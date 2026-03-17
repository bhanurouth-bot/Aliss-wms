# src/models/customer.py
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base

class Customer(Base):
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    
    customer_type = Column(String, default="B2C") # "B2B" or "B2C"
    
    # B2B Specifics
    company_name = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    
    # Addresses
    billing_address = Column(String, nullable=True)
    shipping_address = Column(String, nullable=True)
    
    # Financials
    outstanding_balance = Column(Float, default=0.0) # Tracks unpaid debt!
    lifetime_value = Column(Float, default=0.0)      # Total amount they've spent with you
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    orders = relationship("Order", back_populates="customer", cascade="all, delete-orphan")