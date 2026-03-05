# src/services/order_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException

# --- 1. WE MUST IMPORT QCStatus HERE! ---
from src.models.inventory import Inventory, ProductBatch, QCStatus 
from src.models.order import Order, OrderItem, OrderStatus
from src.schemas.order import OrderCreate
from src.services.wms_svc import generate_picklist

def create_order_with_fefo_reservation(db: Session, order_in: OrderCreate, allow_backorder: bool = False):
    """Creates an order. If allow_backorder is True, it secures what it can and flags the rest."""
    
    db_order = Order(customer_name=order_in.customer_name)
    db.add(db_order)
    db.flush() 
    
    allocations = [] 
    is_backordered = False
    
    for item in order_in.items:
        db_item = OrderItem(order_id=db_order.id, product_id=item.product_id, qty_ordered=item.qty)
        db.add(db_item)
        
        # --- 2. THE SHIELD IS ACTIVATED ---
        inventory_records = (
            db.query(Inventory)
            .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
            .filter(
                Inventory.product_id == item.product_id, 
                Inventory.qty_available > 0,
                Inventory.qc_status == QCStatus.AVAILABLE # <--- THIS STOPS RECALLED STOCK!
            )
            .order_by(ProductBatch.expiry_date.asc())
            .with_for_update() 
            .all()
        )
        
        remaining_qty_to_reserve = item.qty
        
        for inv in inventory_records:
            if remaining_qty_to_reserve <= 0:
                break
                
            qty_to_take = min(inv.qty_available, remaining_qty_to_reserve)
            
            inv.qty_available -= qty_to_take
            inv.qty_reserved += qty_to_take
            remaining_qty_to_reserve -= qty_to_take
            
            allocations.append({
                "product_id": item.product_id,
                "bin_id": inv.bin_id,
                "batch_id": inv.batch_id,
                "qty": qty_to_take
            })
            
        qty_allocated = item.qty - remaining_qty_to_reserve
        db_item.qty_allocated = qty_allocated
        db_item.qty_backordered = remaining_qty_to_reserve
        
        if remaining_qty_to_reserve > 0:
            if not allow_backorder:
                db.rollback() 
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient safe stock for Product ID {item.product_id}. Missing {remaining_qty_to_reserve} units."
                )
            else:
                is_backordered = True
                
    if is_backordered:
        db_order.status = OrderStatus.BACKORDERED
            
    if allocations:
        generate_picklist(db, db_order.id, allocations)
            
    db.commit()
    db.refresh(db_order)
    return db_order

def allocate_backordered_order(db: Session, order_id: int):
    """Attempts to fulfill missing items for a backordered sales order."""
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.status != OrderStatus.BACKORDERED:
        raise HTTPException(status_code=400, detail="Order is not in BACKORDERED status.")
        
    allocations = [] 
    still_backordered = False
    
    for item in order.items:
        if item.qty_backordered <= 0:
            continue 
            
        # --- 3. THE SHIELD PROTECTS BACKORDERS TOO ---
        inventory_records = (
            db.query(Inventory)
            .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
            .filter(
                Inventory.product_id == item.product_id, 
                Inventory.qty_available > 0,
                Inventory.qc_status == QCStatus.AVAILABLE # <--- BOOM! Protected.
            )
            .order_by(ProductBatch.expiry_date.asc())
            .with_for_update() 
            .all()
        )
        
        remaining_to_fulfill = item.qty_backordered
        
        for inv in inventory_records:
            if remaining_to_fulfill <= 0:
                break
                
            qty_to_take = min(inv.qty_available, remaining_to_fulfill)
            
            inv.qty_available -= qty_to_take
            inv.qty_reserved += qty_to_take
            remaining_to_fulfill -= qty_to_take
            
            allocations.append({
                "product_id": item.product_id,
                "bin_id": inv.bin_id,
                "batch_id": inv.batch_id,
                "qty": qty_to_take
            })
            
        fulfilled_this_time = item.qty_backordered - remaining_to_fulfill
        item.qty_allocated += fulfilled_this_time
        item.qty_backordered = remaining_to_fulfill
        
        if item.qty_backordered > 0:
            still_backordered = True
            
    if allocations:
        generate_picklist(db, order.id, allocations)
        
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