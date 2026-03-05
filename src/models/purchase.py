# src/models/purchase.py
import enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base

class POStatus(enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"                     # Sent to supplier, awaiting delivery
    PARTIAL_RECEIVED = "PARTIAL_RECEIVED" # Supplier short-shipped us
    COMPLETED = "COMPLETED"               # We received exactly what we ordered
    CANCELLED = "CANCELLED"

class Supplier(Base):
    __tablename__ = 'suppliers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    contact_email = Column(String)
    phone = Column(String)

class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'
    id = Column(Integer, primary_key=True, index=True)
    po_number = Column(String, unique=True, index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    
    status = Column(SQLEnum(POStatus), default=POStatus.ISSUED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    supplier = relationship("Supplier")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")
    grns = relationship("GRN", back_populates="purchase_order")

class PurchaseOrderItem(Base):
    __tablename__ = 'purchase_order_items'
    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(Integer, ForeignKey('purchase_orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty_ordered = Column(Float)
    qty_received = Column(Float, default=0.0) # Ledger to track short-ships
    unit_cost = Column(Float)                 # What we paid the supplier
    
    purchase_order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product")

class GRN(Base):
    """Goods Receipt Note - The official ledger of what actually arrived on the truck."""
    __tablename__ = 'grns'
    id = Column(Integer, primary_key=True, index=True)
    grn_number = Column(String, unique=True, index=True)
    po_id = Column(Integer, ForeignKey('purchase_orders.id'))
    
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(String, nullable=True)
    
    purchase_order = relationship("PurchaseOrder", back_populates="grns")
    items = relationship("GRNItem", back_populates="grn", cascade="all, delete-orphan")

class GRNItem(Base):
    __tablename__ = 'grn_items'
    id = Column(Integer, primary_key=True, index=True)
    grn_id = Column(Integer, ForeignKey('grns.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    bin_id = Column(Integer, ForeignKey('bins.id')) # Exactly where the worker put it
    
    qty_received = Column(Float)
    
    grn = relationship("GRN", back_populates="items")