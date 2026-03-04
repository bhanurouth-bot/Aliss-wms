# src/services/manufacturing_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta
from src.models.manufacturing import ProductionOrder, BillOfMaterial, ProductionStatus
from src.models.inventory import Inventory, ProductBatch
from src.services.audit_svc import log_activity

def complete_production_order(db: Session, order_id: int):
    """Consumes raw materials and generates the finished goods."""
    
    order = db.query(ProductionOrder).filter(ProductionOrder.id == order_id).first()
    if not order or order.status == ProductionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Invalid or already completed Production Order.")

    bom = db.query(BillOfMaterial).filter(BillOfMaterial.id == order.bom_id).first()

    # 1. CONSUME RAW MATERIALS (Simplified auto-deduction for this tutorial)
    for item in bom.items:
        total_needed = item.qty_required * order.qty_to_produce
        
        # Find available inventory for this raw material
        raw_inventory = db.query(Inventory).filter(
            Inventory.product_id == item.component_product_id,
            Inventory.qty_available > 0
        ).all()
        
        remaining_to_consume = total_needed
        for inv in raw_inventory:
            if remaining_to_consume <= 0:
                break
                
            take_qty = min(inv.qty_available, remaining_to_consume)
            inv.qty_available -= take_qty
            remaining_to_consume -= take_qty
            
        if remaining_to_consume > 0:
            db.rollback()
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient raw materials! Missing {remaining_to_consume} of Product ID {item.component_product_id}"
            )

    # 2. CREATE NEW BATCH FOR FINISHED GOOD
    # E.g., Expiry is 1 year from production date
    new_batch_number = f"MFG-{datetime.now().strftime('%Y%m%d%H%M')}-{order.id}"
    new_batch = ProductBatch(
        product_id=bom.product_id,
        batch_number=new_batch_number,
        expiry_date=datetime.now() + timedelta(days=365) 
    )
    db.add(new_batch)
    db.flush() # Get the batch ID

    # 3. ADD FINISHED GOODS TO INVENTORY
    finished_inventory = Inventory(
        product_id=bom.product_id,
        bin_id=order.destination_bin_id,
        batch_id=new_batch.id,
        qty_available=order.qty_to_produce
    )
    db.add(finished_inventory)

    # 4. UPDATE ORDER STATUS
    order.status = ProductionStatus.COMPLETED
    order.produced_batch_id = new_batch.id

    # 5. IMMUTABLE AUDIT LOG
    log_audit(
        db=db,
        entity_type="ProductionOrder",
        entity_id=order.id,
        action="COMPLETED",
        after_data={"qty_produced": order.qty_to_produce, "batch_number": new_batch_number}
    )

    db.commit()
    db.refresh(order)
    return order