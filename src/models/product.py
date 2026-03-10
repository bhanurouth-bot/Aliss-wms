# src/models/product.py
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from src.core.database import Base

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)
    barcode = Column(String, unique=True, index=True)
    unit_type = Column(String)
    requires_batch_tracking = Column(Boolean, default=False)
    
    # --- NEW: HSN & Brand ---
    hsn_code = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    
    # Pricing & Taxes
    mrp = Column(Float)
    base_price = Column(Float) # Auto-calculated: MRP - Taxes
    discount_percent = Column(Float, default=0.0) # e.g., 15.0 for a 15% off sale
    
    # --- REPLACED: gst_percent split into CGST and SGST ---
    cgst_percent = Column(Float, default=0.0) 
    sgst_percent = Column(Float, default=0.0)
    
    # --- RETAINED: Your Dimensional Logic ---
    weight_kg = Column(Float, default=0.0)
    length_cm = Column(Float, default=0.0)
    width_cm = Column(Float, default=0.0)
    height_cm = Column(Float, default=0.0)
    
    # Kit Logistics
    is_kit = Column(Boolean, default=False)
    components = relationship(
        "KitComponent", 
        foreign_keys="[KitComponent.kit_id]", 
        back_populates="kit", 
        cascade="all, delete-orphan"
    )

class KitComponent(Base):
    """The Bill of Materials (BOM) linking a Kit to its physical items."""
    __tablename__ = 'kit_components'
    id = Column(Integer, primary_key=True, index=True)
    
    kit_id = Column(Integer, ForeignKey('products.id'))
    component_id = Column(Integer, ForeignKey('products.id'))
    qty = Column(Float) # How many of this component are required for 1 Kit?
    
    kit = relationship("Product", foreign_keys=[kit_id], back_populates="components")
    component = relationship("Product", foreign_keys=[component_id])