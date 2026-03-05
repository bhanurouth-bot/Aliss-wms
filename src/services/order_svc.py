# src/services/order_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from src.models.inventory import Inventory, ProductBatch
from src.models.order import Order, OrderItem, OrderStatus
from src.models.product import Product
from src.schemas.order import OrderCreate
from src.services.wms_svc import generate_picklist

def create_order_with_fefo_reservation(db: Session, order_in: OrderCreate, allow_backorder: bool = False):
    
    db_order = Order(customer_name=order_in.customer_name)
    db.add(db_order)
    db.flush() 
    
    allocations = [] 
    is_backordered = False 
    
    for item in order_in.items:
        db_item = OrderItem(order_id=db_order.id, product_id=item.product_id, qty_ordered=item.qty)
        db.add(db_item)
        
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        # --- NEW: EXPLODE THE BOM IF IT'S A KIT ---
        components_to_fulfill = []
        if product.is_kit:
            for comp in product.components:
                components_to_fulfill.append({
                    "product_id": comp.component_id,
                    "qty_needed": comp.qty * item.qty, # e.g., 2 Kits * 3 Toys = 6 Toys needed
                    "comp_qty_per_kit": comp.qty
                })
        else:
            components_to_fulfill.append({
                "product_id": item.product_id,
                "qty_needed": item.qty,
                "comp_qty_per_kit": 1.0
            })

        # We assume we can fulfill everything, and lower this number if we miss parts
        min_kits_fulfilled = item.qty 

        # --- THE FEFO LOOP (Now works on components!) ---
        for comp in components_to_fulfill:
            inventory_records = (
                db.query(Inventory)
                .outerjoin(ProductBatch, Inventory.batch_id == ProductBatch.id)
                .filter(Inventory.product_id == comp["product_id"], Inventory.qty_available > 0)
                .order_by(ProductBatch.expiry_date.asc())
                .with_for_update() 
                .all()
            )
            
            remaining_to_reserve = comp["qty_needed"]
            
            for inv in inventory_records:
                if remaining_to_reserve <= 0:
                    break
                    
                qty_to_take = min(inv.qty_available, remaining_to_reserve)
                
                inv.qty_available -= qty_to_take
                inv.qty_reserved += qty_to_take
                remaining_to_reserve -= qty_to_take
                
                allocations.append({
                    "product_id": comp["product_id"], # Send the warehouse worker for the COMPONENT!
                    "bin_id": inv.bin_id,
                    "batch_id": inv.batch_id,
                    "qty": qty_to_take
                })
                
            # Calculate how many full kits we secured based on this specific component
            qty_found = comp["qty_needed"] - remaining_to_reserve
            kits_fulfilled_from_this_comp = qty_found / comp["comp_qty_per_kit"]
            
            if kits_fulfilled_from_this_comp < min_kits_fulfilled:
                min_kits_fulfilled = kits_fulfilled_from_this_comp

        # Update the Order Item tracking
        db_item.qty_allocated = min_kits_fulfilled
        db_item.qty_backordered = item.qty - min_kits_fulfilled
        
        if db_item.qty_backordered > 0:
            if not allow_backorder:
                db.rollback() 
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient stock to fulfill Order Item. Missing components for {product.name}."
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