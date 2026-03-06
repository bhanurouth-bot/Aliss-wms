# src/services/order_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import func

from src.models.inventory import Inventory, ProductBatch, QCStatus 
from src.models.order import Order, OrderItem, OrderStatus, CustomerType
from src.schemas.order import OrderCreate
from src.services.wms_svc import generate_picklist
from src.models.product import Product

def create_order_with_fefo_reservation(db: Session, order_in: OrderCreate, allow_backorder: bool = False):
    """Creates an order. Explodes Kits into components and secures physical inventory via FEFO."""
    
    is_single_sku = len(order_in.items) == 1

    db_order = Order(
        customer_name=order_in.customer_name,
        order_type=CustomerType(order_in.order_type),
        route=order_in.route,
        is_single_sku=is_single_sku
    )
    db.add(db_order)
    db.flush() 
    
    allocations = [] 
    is_backordered = False
    
    for item in order_in.items:
        db_item = OrderItem(order_id=db_order.id, product_id=item.product_id, qty_ordered=item.qty)
        db.add(db_item)
        
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found.")

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

        kit_fully_allocated = True
        
        # --- 2. THE FEFO SHIELD ---
        for comp_req in components_to_allocate:
            inventory_records = (
                db.query(Inventory)
                .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
                .filter(
                    Inventory.product_id == comp_req["product_id"], 
                    Inventory.qty_available > 0,
                    Inventory.qc_status == QCStatus.AVAILABLE # THE SHIELD
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
                
                inv.qty_available -= qty_to_take
                inv.qty_reserved += qty_to_take
                remaining_qty_to_reserve -= qty_to_take
                
                allocations.append({
                    "product_id": comp_req["product_id"],
                    "bin_id": inv.bin_id,
                    "batch_id": inv.batch_id,
                    "qty": qty_to_take
                })
            
            # If any component of the kit is missing, the whole kit fails!
            if remaining_qty_to_reserve > 0:
                kit_fully_allocated = False
                
        # --- 3. APPLY TO ORDER STATUS ---
        if not kit_fully_allocated:
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
        else:
            db_item.qty_allocated = item.qty
            db_item.qty_backordered = 0
            
    if is_backordered:
        db_order.status = OrderStatus.BACKORDERED
            
    if allocations:
        generate_picklist(db, db_order.id, allocations)
            
    db.commit()
    db.refresh(db_order)
    return db_order

def allocate_backordered_order(db: Session, order_id: int):
    """Attempts to fulfill missing items (and exploded kits) for a backordered sales order."""
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != OrderStatus.BACKORDERED:
        raise HTTPException(status_code=400, detail="Order is not in BACKORDERED status.")
        
    allocations = [] 
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
        
        # PRE-CHECK: Do we have enough inventory for ALL components? (All or nothing!)
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
            
        # If we have enough for the whole kit, execute the physical reservation
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
                
                allocations.append({
                    "product_id": comp_req["product_id"],
                    "bin_id": inv.bin_id,
                    "batch_id": inv.batch_id,
                    "qty": qty_to_take
                })
                
        item.qty_allocated += item.qty_backordered
        item.qty_backordered = 0
        
    if allocations:
        generate_picklist(db, order.id, allocations)
        
    if not still_backordered:
        order.status = OrderStatus.PENDING 
        
    db.commit()
    db.refresh(order)
    return order

def auto_cross_dock(db: Session, product_id: int):
    # Keep your existing auto_cross_dock function here...
    pass