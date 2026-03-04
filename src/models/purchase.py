# src/models/purchase.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from src.core.database import Base

class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'
    id = Column(Integer, primary_key=True, index=True)
    supplier_name = Column(String)
    status = Column(String, default="DRAFT") # DRAFT, APPROVED, RECEIVED
    
    items = relationship("POItem", back_populates="po")

class POItem(Base):
    __tablename__ = 'po_items'
    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(Integer, ForeignKey('purchase_orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    qty_ordered = Column(Float)
    
    po = relationship("PurchaseOrder", back_populates="items")