# src/models/inventory.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from src.core.database import Base

class ProductBatch(Base):
    __tablename__ = 'product_batches'
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), index=True)
    batch_number = Column(String, unique=True, index=True)
    expiry_date = Column(DateTime, index=True) # Critical for FEFO

class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), index=True)
    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=True)
    bin_id = Column(Integer, ForeignKey('bins.id'), index=True)
    
    qty_available = Column(Float, default=0.0)
    qty_reserved = Column(Float, default=0.0) # Used when an order comes in but isn't shipped yet
    
class InventoryAdjustment(Base):
    """Financial and operational audit trail for cycle counts and shrinkage."""
    __tablename__ = 'inventory_adjustments'
    
    id = Column(Integer, primary_key=True, index=True)
    inventory_id = Column(Integer, ForeignKey('inventory.id'))
    
    previous_qty = Column(Float)
    new_qty = Column(Float)
    variance = Column(Float) # Negative means shrinkage (loss), Positive means found stock
    
    reason = Column(String) # e.g., "CYCLE_COUNT", "DAMAGED", "THEFT"
    worker_id = Column(String) # Who recorded the adjustment
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    inventory = relationship("Inventory")