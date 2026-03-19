# src/services/order_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import func

from src.models.inventory import Inventory, ProductBatch, QCStatus 
from src.models.order import Order, OrderItem, OrderStatus, CustomerType
from src.schemas.order import OrderCreate
from src.models.product import Product
from src.models.customer import Customer

# --- IMPORT THESE NEW MODELS ---
from src.models.wms_ops import PickTask, TaskStatus

def create_order_with_fefo_reservation(db: Session, order_in: OrderCreate, allow_backorder: bool = False):
    """Creates an order, links/creates the CRM Customer, explodes Kits, and secures physical inventory."""
    
    is_single_sku = len(order_in.items) == 1

    # ==========================================
    # 1. SMART CUSTOMER LOOKUP / CREATION (CRM)
    # ==========================================
    db_customer = None
    
    # Try to find existing customer by Email or Phone
    if getattr(order_in, 'email', None):
        db_customer = db.query(Customer).filter(Customer.email == order_in.email).first()
    if not db_customer and getattr(order_in, 'phone', None):
        db_customer = db.query(Customer).filter(Customer.phone == order_in.phone).first()
        
    # If they don't exist, create a new Customer profile automatically!
    if not db_customer:
        db_customer = Customer(
            name=order_in.customer_name,
            email=getattr(order_in, 'email', None),
            phone=getattr(order_in, 'phone', None),
            customer_type=order_in.order_type,
            company_name=getattr(order_in, 'company_name', None),
            tax_id=getattr(order_in, 'tax_id', None),
            billing_address=getattr(order_in, 'billing_address', None),
            shipping_address=getattr(order_in, 'shipping_address', None)
        )
        db.add(db_customer)
        db.flush() # Save to get the customer.id immediately

    # ==========================================
    # 2. CREATE THE ORDER (Linked to CRM)
    # ==========================================
    db_order = Order(
        customer_id=db_customer.id, # <--- Link it to the CRM here!
        customer_name=order_in.customer_name,
        email=getattr(order_in, 'email', None),
        phone=getattr(order_in, 'phone', None),
        billing_address=getattr(order_in, 'billing_address', None),
        shipping_address=getattr(order_in, 'shipping_address', None),
        company_name=getattr(order_in, 'company_name', None),
        tax_id=getattr(order_in, 'tax_id', None),
        order_type=CustomerType(order_in.order_type),
        route=order_in.route,
        is_single_sku=is_single_sku
    )
    db.add(db_order)
    db.flush() # Flushes so we get db_order.id
    
    is_backordered = False
    
    for item in order_in.items:
        db_item = OrderItem(order_id=db_order.id, product_id=item.product_id, qty_ordered=item.qty)
        db.add(db_item)
        
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found.")

        # --- 1. KIT EXPLOSION ALGORITHM ---
        # --- 1. KIT EXPLOSION ALGORITHM ---
        components_to_allocate = []
        if product.is_kit and product.components:
            for comp in product.components:
                components_to_allocate.append({
                    "product_id": comp.component_id,
                    "qty_needed": comp.qty * item.qty
                })
        else:
            components_to_allocate.append({
                "product_id": item.product_id,
                "qty_needed": item.qty
            })

        # ==========================================
        # --- NEW: THE PRE-CHECK SHIELD ---
        # ==========================================
        kit_fully_allocated = True
        for comp_req in components_to_allocate:
            available_stock = db.query(func.sum(Inventory.qty_available)).filter(
                Inventory.product_id == comp_req["product_id"],
                Inventory.qc_status == QCStatus.AVAILABLE
            ).scalar() or 0.0
            
            if available_stock < comp_req["qty_needed"]:
                kit_fully_allocated = False
                break

        # ==========================================
        # --- 2. THE FEFO MUTATION (Only runs if safe!) ---
        # ==========================================
        if kit_fully_allocated:
            for comp_req in components_to_allocate:
                inventory_records = (
                    db.query(Inventory)
                    .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
                    .filter(
                        Inventory.product_id == comp_req["product_id"], 
                        Inventory.qty_available > 0,
                        Inventory.qc_status == QCStatus.AVAILABLE
                    )
                    .order_by(ProductBatch.expiry_date.asc())
                    .with_for_update() 
                    .all()
                )
                
                remaining_qty_to_reserve = comp_req["qty_needed"]
                
                for inv in inventory_records:
                    if remaining_qty_to_reserve <= 0:
                        break
                        
                    qty_to_take = min(inv.qty_available, remaining_qty_to_reserve)
                    
                    # Physical inventory reservation
                    inv.qty_available -= qty_to_take
                    inv.qty_reserved += qty_to_take
                    remaining_qty_to_reserve -= qty_to_take
                    
                    # --- REAL LOGIC: CREATE THE INITIAL PICK TASK ---
                    initial_task = PickTask(
                        order_id=db_order.id,
                        product_id=comp_req["product_id"],
                        bin_id=inv.bin_id,
                        batch_id=inv.batch_id,
                        qty_expected=qty_to_take,
                        qty_picked=0.0,
                        status=TaskStatus.PENDING
                    )
                    db.add(initial_task)

            db_item.qty_allocated = item.qty
            db_item.qty_backordered = 0
            
        # --- 3. APPLY TO ORDER STATUS ---
        else:
            if not allow_backorder:
                db.rollback() 
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient safe stock for Product ID {item.product_id}. Check if physical components are in stock."
                )
            else:
                is_backordered = True
                db_item.qty_allocated = 0
                db_item.qty_backordered = item.qty
            
    if is_backordered:
        db_order.status = OrderStatus.BACKORDERED
            
    db.commit()
    db.refresh(db_order)
    return db_order


def allocate_backordered_order(db: Session, order_id: int):
    """Attempts to fulfill missing items (and exploded kits) for a backordered sales order."""
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != OrderStatus.BACKORDERED:
        raise HTTPException(status_code=400, detail="Order is not in BACKORDERED status.")
        
    still_backordered = False
    
    for item in order.items:
        if item.qty_backordered <= 0:
            continue 
            
        product = db.query(Product).filter(Product.id == item.product_id).first()
        components_to_allocate = []
        if product.is_kit and product.components:
            for comp in product.components:
                components_to_allocate.append({
                    "product_id": comp.component_id,
                    "qty_needed": comp.qty * item.qty_backordered
                })
        else:
            components_to_allocate.append({
                "product_id": item.product_id,
                "qty_needed": item.qty_backordered
            })

        kit_fully_allocated = True
        
        for comp_req in components_to_allocate:
            available_stock = db.query(func.sum(Inventory.qty_available)).filter(
                Inventory.product_id == comp_req["product_id"],
                Inventory.qc_status == QCStatus.AVAILABLE
            ).scalar() or 0.0
            
            if available_stock < comp_req["qty_needed"]:
                kit_fully_allocated = False
                break
                
        if not kit_fully_allocated:
            still_backordered = True
            continue 
            
        for comp_req in components_to_allocate:
            inventory_records = (
                db.query(Inventory)
                .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
                .filter(
                    Inventory.product_id == comp_req["product_id"], 
                    Inventory.qty_available > 0,
                    Inventory.qc_status == QCStatus.AVAILABLE 
                )
                .order_by(ProductBatch.expiry_date.asc())
                .with_for_update() 
                .all()
            )
            
            remaining_to_fulfill = comp_req["qty_needed"]
            
            for inv in inventory_records:
                if remaining_to_fulfill <= 0:
                    break
                    
                qty_to_take = min(inv.qty_available, remaining_to_fulfill)
                
                inv.qty_available -= qty_to_take
                inv.qty_reserved += qty_to_take
                remaining_to_fulfill -= qty_to_take
                
                # --- REAL LOGIC: CREATE THE BACKORDER PICK TASK ---
                backorder_task = PickTask(
                    order_id=order.id,
                    product_id=comp_req["product_id"],
                    bin_id=inv.bin_id,
                    batch_id=inv.batch_id,
                    qty_expected=qty_to_take,
                    qty_picked=0.0,
                    status=TaskStatus.PENDING
                )
                db.add(backorder_task)
                
        item.qty_allocated += item.qty_backordered
        item.qty_backordered = 0
        
    if not still_backordered:
        order.status = OrderStatus.PENDING 
        
    db.commit()
    db.refresh(order)
    return order

def auto_cross_dock(db: Session, product_id: int):
    """Sweeps the Backorder queue for any orders waiting on this product."""
    backordered_orders = (
        db.query(Order)
        .join(OrderItem)
        .filter(
            Order.status == OrderStatus.BACKORDERED,
            OrderItem.product_id == product_id,
            OrderItem.qty_backordered > 0
        )
        .order_by(Order.id.asc()) 
        .all()
    )

    cross_docked_order_ids = []
    
    for order in backordered_orders:
        allocate_backordered_order(db, order.id)
        db.refresh(order)
        if order.status != OrderStatus.BACKORDERED:
            cross_docked_order_ids.append(order.id)

    return cross_docked_order_ids