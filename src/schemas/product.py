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
    
    hsn_code: Optional[str] = None
    brand: Optional[str] = None
    
    mrp: float
    
    # --- NEW: Now required from the user during creation ---
    base_price: float 
    
    discount_percent: float = 0.0
    cgst_percent: float = 0.0
    sgst_percent: float = 0.0
    
    is_kit: bool = False
    
    weight_kg: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0

class ProductCreate(ProductBase):
    components: Optional[List[KitComponentCreate]] = None 

class ProductResponse(ProductBase):
    id: int
    # Removed base_price from here since it is now inherited from ProductBase
    components: Optional[List[KitComponentResponse]] = []
    
    model_config = {"from_attributes": True}