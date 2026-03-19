# src/api/app_pull.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from src.core.database import get_db
from src.core.security import require_role
from src.models.wms_ops import WarehouseTask, TaskStatus
from src.models.auth import User

router = APIRouter(prefix="/app/pull", tags=["PULL APP (Contractors)"])

def require_pull_access(current_user = Depends(require_role(["Warehouse Staff"]))):
    """Strictly locks this API to Part-Time workers."""
    if getattr(current_user, 'employment_type', 'FULL_TIME') != 'PART_TIME':
        raise HTTPException(status_code=403, detail="Push App users cannot use the Pull App.")
    return current_user

# Inside src/api/app_pull.py
@router.get("/queue")
def get_pull_queue(task_type: Optional[str] = None, db: Session = Depends(get_db), worker = Depends(require_pull_access)):
    query = db.query(WarehouseTask).filter(
        WarehouseTask.status == TaskStatus.PENDING,
        WarehouseTask.assigned_to == None,
        WarehouseTask.claimed_by == None
    )
    
    if task_type:
        query = query.filter(WarehouseTask.task_type == task_type)
        
    # --- THE MAGIC SORTING ---
    # Sorts descending by priority (3, 2, 1), then ascending by ID (oldest first)
    return query.order_by(WarehouseTask.priority.desc(), WarehouseTask.id.asc()).all()

@router.post("/{task_id}/start-timer")
def claim_and_start_task(task_id: int, db: Session = Depends(get_db), worker = Depends(require_pull_access)):
    """Worker clicks 'Start'. It claims the task and starts the un-cheatable backend clock."""
    task = db.query(WarehouseTask).filter(WarehouseTask.id == task_id).with_for_update().first()
    
    if task.claimed_by or task.assigned_to:
        raise HTTPException(status_code=409, detail="Task is no longer available.")
        
    task.claimed_by = worker.id
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = datetime.now() # START THE CLOCK
    db.commit()
    
    return {
        "message": "Timer started!", 
        "target_seconds": task.target_time_seconds,
        "started_at": task.started_at
    }