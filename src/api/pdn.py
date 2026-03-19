# src/api/pdn.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, timedelta

from src.core.database import get_db
from src.core.security import require_role
from src.models.inventory import Inventory, ProductBatch, QCStatus
from src.models.wms_ops import PickTask, TaskStatus

router = APIRouter(prefix="/pdn", tags=["PDN & Expiry Management"])

@router.post("/generate-expiry-picks")
def generate_expiry_pull_tasks(
    days_to_expiry: int = 30, # Look ahead 30 days by default
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "PDN Manager"]))
):
    """Sweeps the warehouse for expiring stock and generates tasks to pull it off the shelf."""
    
    target_date = date.today() + timedelta(days=days_to_expiry)
    
    # 1. Hunt down the expiring physical inventory
    expiring_inventory = (
        db.query(Inventory, ProductBatch)
        .join(ProductBatch, Inventory.batch_id == ProductBatch.id)
        .filter(
            Inventory.qty_available > 0,
            ProductBatch.expiry_date <= target_date,
            Inventory.qc_status == QCStatus.AVAILABLE # Only pull stuff that is currently active
        )
        .all()
    )
    
    tasks_generated = 0
    
    for inv, batch in expiring_inventory:
        # 2. Lock the inventory so it can't be sold!
        inv.qc_status = QCStatus.QUARANTINED 
        
        # 3. Generate a special Pull-Model task for the workers
        pull_task = PickTask(
            order_id=None, # Not for a customer!
            product_id=inv.product_id,
            bin_id=inv.bin_id,
            batch_id=inv.batch_id,
            qty_expected=inv.qty_available,
            qty_picked=0.0,
            status=TaskStatus.PENDING,
            
            # --- THE NEW LMS COLUMNS ---
            task_type="EXPIRY_PULL", # Routes it to the PDN Module Queue
            assigned_to=None         # Leaves it open for the Pull model
        )
        db.add(pull_task)
        tasks_generated += 1
        
    db.commit()
    
    return {
        "message": f"Expiry sweep complete. Locked {tasks_generated} expiring bins.",
        "tasks_generated": tasks_generated
    }