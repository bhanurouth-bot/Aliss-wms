# src/models/billing.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from src.core.database import Base

class InvoiceStatus(enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"

class Invoice(Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True)
    invoice_number = Column(String, unique=True, index=True)
    
    subtotal = Column(Float, default=0.0)
    tax_total = Column(Float, default=0.0)
    grand_total = Column(Float, default=0.0)
    
    currency = Column(String, default="USD")
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.UNPAID)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceItem(Base):
    __tablename__ = 'invoice_items'
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty = Column(Float)
    unit_base_price = Column(Float) # Pre-tax unit price
    tax_amount = Column(Float)      # Tax charged for this specific line
    line_total = Column(Float)      # Final amount including tax (Qty * MRP)
    
    invoice = relationship("Invoice", back_populates="items")