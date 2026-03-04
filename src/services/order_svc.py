# src/services/order_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from src.models.inventory import Inventory, ProductBatch
from src.models.order import Order, OrderItem, OrderStatus
from src.schemas.order import OrderCreate
from src.services.wms_svc import generate_picklist

def create_order_with_fefo_reservation(db: Session, order_in: OrderCreate, allow_backorder: bool = False):
    """Creates an order. If allow_backorder is True, it secures what it can and flags the rest."""
    
    db_order = Order(customer_name=order_in.customer_name)
    db.add(db_order)
    db.flush() 
    
    allocations = [] 
    is_backordered = False # Flag to track if the whole order needs to be paused
    
    for item in order_in.items:
        db_item = OrderItem(order_id=db_order.id, product_id=item.product_id, qty_ordered=item.qty)
        db.add(db_item)
        
        inventory_records = (
            db.query(Inventory)
            .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
            .filter(Inventory.product_id == item.product_id, Inventory.qty_available > 0)
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
            
        # --- NEW BACKORDER LOGIC ---
        qty_allocated = item.qty - remaining_qty_to_reserve
        db_item.qty_allocated = qty_allocated
        db_item.qty_backordered = remaining_qty_to_reserve
        
        if remaining_qty_to_reserve > 0:
            if not allow_backorder:
                db.rollback() 
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient stock for Product ID {item.product_id}. Missing {remaining_qty_to_reserve} units."
                )
            else:
                is_backordered = True
                
    # If we missed any items, flag the entire order status
    if is_backordered:
        db_order.status = OrderStatus.BACKORDERED
            
    # Only generate a picklist if we actually secured SOME inventory
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
            continue # This item is already fully allocated, skip it!
            
        # Search for available inventory using FEFO logic
        inventory_records = (
            db.query(Inventory)
            .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
            .filter(Inventory.product_id == item.product_id, Inventory.qty_available > 0)
            .order_by(ProductBatch.expiry_date.asc())
            .with_for_update() 
            .all()
        )
        
        remaining_to_fulfill = item.qty_backordered
        
        for inv in inventory_records:
            if remaining_to_fulfill <= 0:
                break
                
            qty_to_take = min(inv.qty_available, remaining_to_fulfill)
            
            # Move from available to reserved
            inv.qty_available -= qty_to_take
            inv.qty_reserved += qty_to_take
            remaining_to_fulfill -= qty_to_take
            
            # Save mapping for the warehouse worker
            allocations.append({
                "product_id": item.product_id,
                "bin_id": inv.bin_id,
                "batch_id": inv.batch_id,
                "qty": qty_to_take
            })
            
        # Update the Order Item tracking
        fulfilled_this_time = item.qty_backordered - remaining_to_fulfill
        item.qty_allocated += fulfilled_this_time
        item.qty_backordered = remaining_to_fulfill
        
        if item.qty_backordered > 0:
            still_backordered = True
            
    # Generate the physical picklist for whatever we just found
    if allocations:
        generate_picklist(db, order.id, allocations)
        
    # If we found everything, update the order status so the warehouse knows it's ready!
    if not still_backordered:
        order.status = OrderStatus.PENDING 
        
    db.commit()
    db.refresh(order)
    return order