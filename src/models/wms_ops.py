# src/models/wms_ops.py
import enum
from sqlalchemy import Column, Integer, ForeignKey, Float, String, Enum as SQLEnum
from sqlalchemy.orm import relationship
from src.core.database import Base

class TaskStatus(enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class PickingWave(Base):
    """A bulk collection of orders grouped by smart filters."""
    __tablename__ = 'picking_waves'
    id = Column(Integer, primary_key=True, index=True)
    wave_name = Column(String) # e.g., "B2B-MORNING-WAVE"
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    orders = relationship("Order", backref="wave")
    tasks = relationship("PickTask", back_populates="wave", cascade="all, delete-orphan")

class PickTask(Base):
    __tablename__ = 'pick_tasks'
    id = Column(Integer, primary_key=True, index=True)
    
    # A task can belong to a single order OR a bulk wave
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True) 
    wave_id = Column(Integer, ForeignKey('picking_waves.id'), nullable=True)
    
    product_id = Column(Integer, ForeignKey('products.id'))
    bin_id = Column(Integer, ForeignKey('bins.id'))
    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=True)
    
    qty_expected = Column(Float)
    qty_picked = Column(Float, default=0.0)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    wave = relationship("PickingWave", back_populates="tasks")