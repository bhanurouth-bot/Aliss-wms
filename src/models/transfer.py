# src/models/transfer.py
from sqlalchemy import Column, Integer, Float, ForeignKey, String, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from src.core.database import Base

class TransferStatus(enum.Enum):
    PENDING = "PENDING"       # Drafted, waiting for warehouse A to pack it
    IN_TRANSIT = "IN_TRANSIT" # On the truck!
    COMPLETED = "COMPLETED"   # Arrived and scanned at warehouse B
    CANCELLED = "CANCELLED"

class TransferOrder(Base):
    __tablename__ = 'transfer_orders'
    id = Column(Integer, primary_key=True, index=True)
    transfer_number = Column(String, unique=True, index=True)
    
    source_warehouse_id = Column(Integer, ForeignKey('warehouses.id'))
    destination_warehouse_id = Column(Integer, ForeignKey('warehouses.id'))
    
    status = Column(SQLEnum(TransferStatus), default=TransferStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    
    items = relationship("TransferOrderItem", back_populates="transfer", cascade="all, delete-orphan")

class TransferOrderItem(Base):
    __tablename__ = 'transfer_order_items'
    id = Column(Integer, primary_key=True, index=True)
    transfer_order_id = Column(Integer, ForeignKey('transfer_orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty_requested = Column(Float)
    qty_shipped = Column(Float, default=0.0)
    qty_received = Column(Float, default=0.0)
    
    transfer = relationship("TransferOrder", back_populates="items")