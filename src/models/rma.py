# src/models/rma.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from src.core.database import Base

class RmaStatus(enum.Enum):
    PENDING = "PENDING"       # Customer requested a return
    RECEIVED = "RECEIVED"     # Box arrived at the warehouse
    INSPECTED = "INSPECTED"   # Worker checked the items
    COMPLETED = "COMPLETED"   # Refund issued / Closed

class ItemCondition(enum.Enum):
    SELLABLE = "SELLABLE"     # Goes back to inventory
    DAMAGED = "DAMAGED"       # Goes to the trash/write-off

class RMA(Base):
    __tablename__ = 'rmas'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    rma_number = Column(String, unique=True, index=True)
    
    status = Column(SQLEnum(RmaStatus), default=RmaStatus.PENDING)
    reason = Column(String) # e.g., "Wrong Size", "Arrived Broken"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    items = relationship("RMAItem", back_populates="rma", cascade="all, delete-orphan")

class RMAItem(Base):
    __tablename__ = 'rma_items'
    id = Column(Integer, primary_key=True, index=True)
    rma_id = Column(Integer, ForeignKey('rmas.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty_returned = Column(Float)
    condition = Column(SQLEnum(ItemCondition), nullable=True) # Set during inspection
    
    rma = relationship("RMA", back_populates="items")