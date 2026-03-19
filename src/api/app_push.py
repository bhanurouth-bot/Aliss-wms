# src/api/app_push.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from src.core.database import get_db
from src.core.security import require_role
from src.models.wms_ops import WarehouseTask, TaskStatus

router = APIRouter(prefix="/app/push", tags=["PUSH APP (Full-Time)"])

def require_push_access(current_user = Depends(require_role(["Warehouse Staff", "Warehouse Manager"]))):
    """Strictly locks this API to Full-Time workers."""
    if getattr(current_user, 'employment_type', 'FULL_TIME') != 'FULL_TIME':
        raise HTTPException(status_code=403, detail="Part-Time workers cannot use the Push App.")
    return current_user

@router.get("/assignments")
def get_my_assignments(db: Session = Depends(get_db), worker = Depends(require_push_access)):
    """Shows tasks strictly pushed to this worker by a manager."""
    return db.query(WarehouseTask).filter(
        WarehouseTask.assigned_to == worker.id,
        WarehouseTask.status == TaskStatus.PENDING
    ).order_by(WarehouseTask.id.asc()).all()

@router.post("/{task_id}/start-timer")
def start_assigned_task(task_id: int, db: Session = Depends(get_db), worker = Depends(require_push_access)):
    """Worker clicks 'Start' on their assigned task to begin the timer."""
    task = db.query(WarehouseTask).filter(WarehouseTask.id == task_id, WarehouseTask.assigned_to == worker.id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not assigned to you.")
        
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.now() # START THE CLOCK
    db.commit()
    
    return {
        "message": "Timer started!", 
        "target_seconds": task.target_time_seconds,
        "started_at": task.started_at
    }