# src/api/wms_ops.py
import os
import json
import redis
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.core.database import get_db
from src.core.security import require_role
from src.services.wms_svc import confirm_pick_task

# --- Safely Initialize Redis Client for WebSockets ---
_raw_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(' \'"\r\n')
_redis_kwargs = {}
if _raw_redis_url.startswith("rediss://"):
    _redis_kwargs["ssl_cert_reqs"] = "none"

redis_client = redis.Redis.from_url(_raw_redis_url, **_redis_kwargs)
# -----------------------------------------------------

# This router now strictly handles physical scanner guns, no LMS queues!
router = APIRouter(prefix="/wms/tasks", tags=["WMS Operations & Scanning"])

class PickScanRequest(BaseModel):
    scanned_bin: str      
    scanned_product: str  
    qty_picked: float     

@router.post("/{task_id}/scan")
def execute_pick_scan(
    task_id: int,
    payload: PickScanRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    The Picker's Barcode Gun Endpoint. 
    Validates physical location and item barcodes before confirming the WAVE pick.
    """
    # 1. Execute the core business logic (verifies bin, verifies product, deducts inventory)
    task = confirm_pick_task(
        db=db,
        task_id=task_id,
        scanned_bin=payload.scanned_bin,
        scanned_product=payload.scanned_product,
        qty_picked=payload.qty_picked,
        worker_id=current_user.id
    )
    
    # 2. 🎉 Broadcast the directed pick to the WebSockets!
    alert = {
        "type": "DIRECTED_TASK_PICK",
        "message": f"TASK COMPLETE: Worker {current_user.id} picked {payload.qty_picked}x of {payload.scanned_product} from {payload.scanned_bin}."
    }
    
    try:
        redis_client.publish("erp_notifications", json.dumps(alert))
    except Exception as e:
        print(f"Warning: Failed to send WebSocket notification: {e}")
    
    return {
        "message": "Scan accepted. Wave Pick confirmed!", 
        "task_id": task.id,
        "wave_id": task.wave_id,
        "status": task.status.name
    }