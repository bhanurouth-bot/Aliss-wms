# src/models/wms_ops.py
import enum
from sqlalchemy import Column, Integer, ForeignKey, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship
from src.core.database import Base

class TaskStatus(enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class Picklist(Base):
    __tablename__ = 'picklists'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    tasks = relationship("PickTask", back_populates="picklist")

class PickTask(Base):
    __tablename__ = 'pick_tasks'
    id = Column(Integer, primary_key=True, index=True)
    picklist_id = Column(Integer, ForeignKey('picklists.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    bin_id = Column(Integer, ForeignKey('bins.id'))
    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=True)
    
    qty_expected = Column(Float)
    qty_picked = Column(Float, default=0.0)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    picklist = relationship("Picklist", back_populates="tasks")