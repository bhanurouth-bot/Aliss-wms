# src/models/wms_ops.py
import enum
from sqlalchemy import Column, Integer, ForeignKey, Float, String, Enum as SQLEnum
from sqlalchemy.orm import relationship
from src.core.database import Base
from sqlalchemy import DateTime
from sqlalchemy.sql import func

class TaskStatus(enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class PickingWave(Base):
    """A bulk collection of orders grouped by smart filters."""
    __tablename__ = 'picking_waves'
    id = Column(Integer, primary_key=True, index=True)
    wave_name = Column(String) 
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    orders = relationship("Order", backref="wave")
    # --- UPDATED RELATIONSHIP ---
    tasks = relationship("WarehouseTask", back_populates="wave", cascade="all, delete-orphan")

# --- RENAMED FROM WarehouseTask ---
class WarehouseTask(Base):
    __tablename__ = 'warehouse_tasks'
    id = Column(Integer, primary_key=True, index=True)
    
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True) 
    wave_id = Column(Integer, ForeignKey('picking_waves.id'), nullable=True)
    
    product_id = Column(Integer, ForeignKey('products.id'))
    bin_id = Column(Integer, ForeignKey('bins.id'))
    batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=True)
    
    qty_expected = Column(Float)
    qty_picked = Column(Float, default=0.0)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    
    # 1 = NORMAL, 2 = URGENT, 3 = VERY URGENT
    priority = Column(Integer, default=1) 
    
    wave = relationship("PickingWave", back_populates="tasks")

    # --- THE HYBRID LMS COLUMNS ---
    task_type = Column(String, default="OUTBOUND_PICK") # 'OUTBOUND_PICK', 'EXPIRY_PULL', 'REPLENISH', 'GRN_PUTAWAY', 'CYCLE_COUNT', 'QC_PACKING'
    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True) 
    claimed_by = Column(Integer, ForeignKey('users.id'), nullable=True)  
    
    worker_id = Column(Integer, ForeignKey('users.id'), nullable=True) 
    target_time_seconds = Column(Integer, default=120) 
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)