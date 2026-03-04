# src/models/audit.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from src.core.database import Base

class AuditLog(Base):
    """Immutable ledger of all system changes."""
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Core Audit Fields matching our Middleware
    username = Column(String, index=True)      # Who did it (e.g., 'admin')
    action = Column(String)                    # HTTP Method or Action ('POST', 'CREATE')
    entity_name = Column(String, index=True)   # The URL path or Entity Name
    entity_id = Column(Integer, index=True)    # The ID of the item affected
    details = Column(String)                   # Human-readable description
    
    # Advanced data tracking (Optional for future use)
    before_data = Column(JSON, nullable=True) 
    after_data = Column(JSON, nullable=True)
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)