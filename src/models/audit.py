# src/models/audit.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from src.core.database import Base

class AuditLog(Base):
    """Immutable ledger of all system changes."""
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, index=True) # e.g., 'Product', 'Inventory', 'Order'
    entity_id = Column(Integer, index=True)
    action = Column(String)                  # 'CREATE', 'UPDATE', 'DELETE'
    
    # Storing the exact state of the data
    before_data = Column(JSON, nullable=True) 
    after_data = Column(JSON, nullable=True)
    
    # Metadata
    performed_by = Column(Integer, index=True, nullable=True) # User ID
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)