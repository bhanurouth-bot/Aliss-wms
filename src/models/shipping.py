# src/models/shipping.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from src.core.database import Base

class Shipment(Base):
    __tablename__ = 'shipments'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True)
    
    carrier = Column(String) # e.g., FedEx, UPS, DHL
    tracking_number = Column(String, unique=True, index=True)
    shipping_method = Column(String) # e.g., Next Day Air, Ground
    
    shipped_at = Column(DateTime(timezone=True), server_default=func.now())