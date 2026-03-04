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
    
    # In a real production environment, we would add Optimistic Locking here