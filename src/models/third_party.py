# src/models/third_party.py
from sqlalchemy import Column, Integer, Float, Date, ForeignKey, String
from datetime import date
from src.core.database import Base

class ClientStorageLog(Base):
    """A nightly snapshot of how much space a client is taking up."""
    __tablename__ = "client_storage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("customers.id"), nullable=False) # The 3PL Client
    record_date = Column(Date, default=date.today, nullable=False)
    
    total_cubic_feet = Column(Float, default=0.0)
    storage_rate_per_cuft = Column(Float, default=0.05) # e.g., $0.05 per cubic foot per day
    daily_fee = Column(Float, default=0.0)