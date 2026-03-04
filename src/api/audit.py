# src/api/audit.py (Updated to require Admin role)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from src.core.database import get_db
from src.models.audit import AuditLog
from src.schemas import audit as schemas
from src.core.security import require_role # <-- Import the magic dependency

router = APIRouter(prefix="/audit", tags=["Compliance & Audit"])

# Lock it down by adding the Depends(require_role([...])) to the parameter list
@router.get("/", response_model=List[schemas.AuditLogResponse])
def get_audit_logs(
    limit: int = 50, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin"])) # <-- THE LOCK
):
    """Fetch the most recent immutable audit logs. (ADMIN ONLY)"""
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()