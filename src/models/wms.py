# src/models/wms.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from src.core.database import Base

class Warehouse(Base):
    __tablename__ = 'warehouses'
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True) # e.g., 'WH-MAIN'
    name = Column(String)
    
    zones = relationship("Zone", back_populates="warehouse")

class Zone(Base):
    __tablename__ = 'zones'
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'))
    code = Column(String, index=True) # e.g., 'COLD-STORAGE'
    type = Column(String) 
    
    warehouse = relationship("Warehouse", back_populates="zones")
    bins = relationship("Bin", back_populates="zone")

class Bin(Base):
    __tablename__ = 'bins'
    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey('zones.id'))
    location_code = Column(String, unique=True, index=True) 
    barcode = Column(String, unique=True, index=True) 
    is_active = Column(Boolean, default=True)
    
    # --- NEW: WAREHOUSE CONSTRAINTS ---
    max_weight_kg = Column(Float, default=1000.0) # How much weight can the shelf hold?
    max_volume_cm3 = Column(Float, default=1000000.0) # How much space is inside?
    
    zone = relationship("Zone", back_populates="bins")

# --- NEW: PACKAGING BOX MODEL ---
class PackagingBox(Base):
    """The catalog of cardboard boxes your company uses to ship orders."""
    __tablename__ = 'packaging_boxes'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True) # e.g., "FedEx Small", "Custom Large"
    
    length_cm = Column(Float)
    width_cm = Column(Float)
    height_cm = Column(Float)
    max_weight_kg = Column(Float) # The box will break if heavier than this
    empty_weight_kg = Column(Float)