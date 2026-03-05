# src/api/qc.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.core.database import get_db
from src.core.security import require_role
from src.models.inventory import Inventory, ProductBatch, QCStatus

router = APIRouter(prefix="/qc", tags=["Quality Control & Holds"])

class BatchHoldRequest(BaseModel):
    batch_id: int
    new_status: str # "QUARANTINED" or "RECALLED" or "AVAILABLE"
    reason: str

@router.post("/batch-hold")
def apply_global_batch_hold(
    payload: BatchHoldRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Compliance Officer"]))
):
    """
    The Kill Switch: Instantly changes the QC status of a specific batch 
    across EVERY bin and warehouse in the entire company.
    """
    try:
        target_status = QCStatus(payload.new_status.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status. Use AVAILABLE, QUARANTINED, or RECALLED.")

    batch = db.query(ProductBatch).filter(ProductBatch.id == payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found.")

    # Find every single bin in the world that holds this batch
    affected_inventory = db.query(Inventory).filter(Inventory.batch_id == batch.id).all()
    
    if not affected_inventory:
        return {"message": f"No physical inventory found for Batch {batch.batch_number}."}

    units_frozen = 0
    for inv in affected_inventory:
        inv.qc_status = target_status
        units_frozen += inv.qty_available
        
        # Note: If stock is already in 'qty_reserved' (meaning it's currently on a picklist),
        # an advanced ERP would also actively cancel those pending PickTasks here! 

    db.commit()
    
    return {
        "message": f"GLOBAL HOLD EXECUTED. {target_status.name} applied to Batch {batch.batch_number}.",
        "bins_affected": len(affected_inventory),
        "total_units_frozen": units_frozen,
        "reason_logged": payload.reason
    }