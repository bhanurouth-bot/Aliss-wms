# src/services/audit_svc.py
from sqlalchemy.orm import Session
from src.models.audit import AuditLog

def log_activity(db: Session, username: str, action: str, entity: str, entity_id: int, details: str = ""):
    """Universally records an action into the immutable audit ledger."""
    log = AuditLog(
        username=username,
        action=action,
        entity_name=entity,
        entity_id=entity_id,
        details=details
    )
    db.add(log)
    db.commit()