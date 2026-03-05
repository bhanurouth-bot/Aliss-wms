# src/api/wms_ops.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.core.database import get_db
from src.core.security import require_role
from src.services.wms_svc import confirm_pick_task

router = APIRouter(prefix="/wms/tasks", tags=["WMS Operations & Scanning"])

class PickScanRequest(BaseModel):
    scanned_bin: str      # The barcode of the physical Bin
    scanned_product: str  # The barcode of the physical Product
    qty_picked: float     # How many they are tossing into the cart

@router.post("/{task_id}/scan")
def execute_pick_scan(
    task_id: int,
    payload: PickScanRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    The Picker's Barcode Gun Endpoint. 
    Validates physical location and item barcodes before confirming the pick.
    """
    task = confirm_pick_task(
        db=db,
        task_id=task_id,
        scanned_bin=payload.scanned_bin,
        scanned_product=payload.scanned_product,
        qty_picked=payload.qty_picked,
        worker_id=current_user.id
    )
    
    return {
        "message": "Scan accepted. Pick confirmed!", 
        "task_id": task.id,
        "status": task.status.name
    }