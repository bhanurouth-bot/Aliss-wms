# src/models/billing.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from src.core.database import Base

class InvoiceStatus(enum.Enum):
    DRAFT = "DRAFT"
    UNPAID = "UNPAID" # Typical for B2B Net-30 terms
    PAID = "PAID"     # Typical for B2C instant checkout
    VOID = "VOID"

class Invoice(Base):
    """The Financial Ledger for an Order."""
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, unique=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True)
    
    # Financial Totals
    subtotal = Column(Float, default=0.0)
    tax_total = Column(Float, default=0.0)
    discount_total = Column(Float, default=0.0)
    grand_total = Column(Float, default=0.0)
    
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.UNPAID)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=True)
    
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    order = relationship("Order")

class InvoiceItem(Base):
    __tablename__ = 'invoice_items'
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty = Column(Float)
    unit_price = Column(Float) # The price actually charged (after B2B discounts)
    tax_amount = Column(Float)
    line_total = Column(Float)
    
    invoice = relationship("Invoice", back_populates="items")