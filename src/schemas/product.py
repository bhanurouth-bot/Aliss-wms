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
    mrp: float
    gst_percent: float
    is_kit: bool = False # <-- NEW

class ProductCreate(ProductBase):
    components: Optional[List[KitComponentCreate]] = None # <-- BOM Input

class ProductResponse(ProductBase):
    id: int
    base_price: float
    components: Optional[List[KitComponentResponse]] = []
    
    model_config = {"from_attributes": True}