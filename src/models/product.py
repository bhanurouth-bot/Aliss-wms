# src/models/product.py (Update)
from sqlalchemy import Column, Integer, String, Boolean, Float
from src.core.database import Base

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    category = Column(String)
    barcode = Column(String, unique=True, index=True)
    unit_type = Column(String)
    
    # --- NEW INCLUSIVE PRICING COLUMNS ---
    mrp = Column(Float, default=0.0)         # The final price the customer pays
    gst_percent = Column(Float, default=0.0) # e.g., 5.0, 12.0, 18.0
    base_price = Column(Float, default=0.0)  # Auto-calculated pre-tax price
    
    requires_batch_tracking = Column(Boolean, default=False)