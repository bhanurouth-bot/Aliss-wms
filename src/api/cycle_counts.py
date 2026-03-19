# src/api/cycle_counts.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.security import require_role
from src.schemas import cycle_count as schemas
from src.models.inventory import Inventory, InventoryAdjustment
from typing import List
from src.services.wms_svc import generate_warehouse_task
from src.models.inventory import Inventory
from src.models.wms import Bin

router = APIRouter(prefix="/cycle-counts", tags=["Inventory Cycle Counting"])

@router.post("/record", response_model=schemas.AdjustmentResponse)
def record_cycle_count(
    payload: schemas.CycleCountRequest, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager"]))
):
    """
    Submits a physical blind count. If a discrepancy is found, it automatically 
    corrects the system inventory and logs the financial variance.
    """
    # 1. Look up the expected inventory
    inv_record = db.query(Inventory).filter(
        Inventory.product_id == payload.product_id,
        Inventory.bin_id == payload.bin_id
    ).with_for_update().first()
    
    previous_qty = inv_record.qty_available if inv_record else 0.0
    new_qty = payload.physical_qty
    variance = new_qty - previous_qty
    
    # 2. If the count is perfectly accurate, we just return a success message
    if variance == 0:
        raise HTTPException(
            status_code=200, 
            detail="Cycle count matches system exactly. No adjustment needed."
        )
        
    # 3. Handle the discrepancy
    if inv_record:
        # Update existing stock
        inv_record.qty_available = new_qty
    else:
        # Found stock where the system thought there was none!
        if new_qty > 0:
            inv_record = Inventory(
                product_id=payload.product_id, 
                bin_id=payload.bin_id, 
                qty_available=new_qty
            )
            db.add(inv_record)
            db.flush() # Flush to get the new inventory.id for our audit log
        else:
            raise HTTPException(status_code=400, detail="Cannot adjust non-existent inventory to zero.")

    # 4. Log the Variance for the Finance and Audit teams
    adjustment = InventoryAdjustment(
        inventory_id=inv_record.id,
        previous_qty=previous_qty,
        new_qty=new_qty,
        variance=variance,
        reason=payload.reason,
        worker_id=current_user.username
    )
    db.add(adjustment)
    
    db.commit()
    db.refresh(adjustment)
    
    return adjustment

@router.post("/generate-audit-tasks/{zone_id}", tags=["Task Makers"])
def generate_zone_audit_tasks(
    zone_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager"]))
):
    """Manager clicks 'Audit Zone'. It creates URGENT tasks for part-timers to count."""
    
    # 1. Find all active inventory sitting in this specific physical zone
    active_inventory = db.query(Inventory).join(Bin, Inventory.bin_id == Bin.id).filter(
        Bin.zone_id == zone_id,
        Inventory.qty_available > 0
    ).all()
    
    tasks_created = 0
    for inv in active_inventory:
        # 2. Fire the Task Maker! 
        generate_warehouse_task(
            db=db,
            task_type="CYCLE_COUNT",
            product_id=inv.product_id,
            bin_id=inv.bin_id,
            qty_expected=0.0, # It's a blind count, so we don't tell the worker what to expect!
            priority=2,       # URGENT: Audits jump to the top of the queue
            batch_id=inv.batch_id,
            target_time_seconds=300 # 5 minutes to count a bin
        )
        tasks_created += 1
        
    db.commit()
    return {"message": f"Successfully generated {tasks_created} blind Cycle Count tasks for Zone {zone_id}."}