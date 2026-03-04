# src/schemas/product.py (Update)
from pydantic import BaseModel

class ProductBase(BaseModel):
    sku: str
    name: str
    category: str
    barcode: str
    unit_type: str
    requires_batch_tracking: bool = False
    mrp: float          # User inputs the final MRP
    gst_percent: float  # User inputs the tax bracket

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    base_price: float   # We return the calculated base price to the user
    
    model_config = {"from_attributes": True}