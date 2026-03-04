# src/models/wms.py
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
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
    
    location_code = Column(String, unique=True, index=True) # e.g., 'A-12-04'
    barcode = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    
    zone = relationship("Zone", back_populates="bins")