# src/services/audit_svc.py
from sqlalchemy.orm import Session
from src.models.audit import AuditLog

def log_audit(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    after_data: dict = None,
    before_data: dict = None,
    performed_by: int = 1,       # Mocking User ID 1 until we build JWT Auth
    ip_address: str = "127.0.0.1" # Mocking local IP
):
    """
    Creates an audit log entry. 
    Notice we DO NOT call db.commit() here! 
    We attach it to the current database session so it commits atomically with the main action.
    """
    audit_entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_data=before_data,
        after_data=after_data,
        performed_by=performed_by,
        ip_address=ip_address
    )
    
    db.add(audit_entry)