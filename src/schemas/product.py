# src/schemas/product.py
from pydantic import BaseModel
from typing import List, Optional

class KitComponentCreate(BaseModel):
    component_id: int
    qty: float

class KitComponentResponse(BaseModel):
    id: int
    component_id: int
    qty: float
    model_config = {"from_attributes": True}

class ProductBase(BaseModel):
    sku: str
    name: str
    category: str
    barcode: str
    unit_type: str
    requires_batch_tracking: bool = False
    
    # --- NEW: HSN & Brand ---
    hsn_code: Optional[str] = "N/A"
    brand: Optional[str] = "N/A"
    
    mrp: float
    # --- REPLACED: gst_percent split into CGST and SGST ---
    cgst_percent: float = 0.0
    sgst_percent: float = 0.0
    
    is_kit: bool = False
    
    # --- RETAINED: Your Dimensional Logic ---
    weight_kg: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0

class ProductCreate(ProductBase):
    components: Optional[List[KitComponentCreate]] = None 

class ProductResponse(ProductBase):
    id: int
    base_price: float
    components: Optional[List[KitComponentResponse]] = []
    
    model_config = {"from_attributes": True}