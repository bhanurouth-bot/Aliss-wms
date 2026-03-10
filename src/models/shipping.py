# src/models/shipping.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
import enum
from src.core.database import Base

class DeliveryStatus(enum.Enum):
    DISPATCHED = "DISPATCHED" # On the truck
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"   # Lost/Damaged

class ShippingManifest(Base):
    """Records the physical dispatch of an order."""
    __tablename__ = 'shipping_manifests'
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True)
    
    carrier = Column(String, index=True)       # e.g., BlueDart, Delhivery, FedEx
    tracking_number = Column(String, unique=True, index=True)
    
    actual_weight_kg = Column(Float, default=0.0) # What the scale at the dock reads
    shipping_cost = Column(Float, default=0.0)    # What the carrier charged you
    
    status = Column(SQLEnum(DeliveryStatus), default=DeliveryStatus.DISPATCHED)
    dispatched_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)