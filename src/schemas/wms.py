# src/schemas/wms.py
from pydantic import BaseModel
from typing import List, Optional

# --- WAREHOUSE SCHEMAS ---
class WarehouseBase(BaseModel):
    code: str
    name: str

class WarehouseCreate(WarehouseBase):
    pass

class WarehouseResponse(WarehouseBase):
    id: int
    
    # Pydantic V2 syntax to tell it to read from SQLAlchemy models
    model_config = {"from_attributes": True}

# --- ZONE SCHEMAS ---
class ZoneBase(BaseModel):
    code: str
    type: str

class ZoneCreate(ZoneBase):
    warehouse_id: int

class ZoneResponse(ZoneBase):
    id: int
    warehouse_id: int
    
    model_config = {"from_attributes": True}

# --- BIN SCHEMAS ---
class BinBase(BaseModel):
    location_code: str  
    barcode: str        
    is_active: bool = True
    
    # --- ADD THESE! ---
    max_weight_kg: float = 1000.0 
    max_volume_cm3: float = 1000000.0

class BinCreate(BinBase):
    zone_id: int

class BinResponse(BinBase):
    id: int
    zone_id: int
    
    model_config = {"from_attributes": True}