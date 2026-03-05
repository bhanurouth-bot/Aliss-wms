# src/schemas/inventory.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# --- BATCH SCHEMAS ---
class ProductBatchCreate(BaseModel):
    product_id: int
    batch_number: str
    expiry_date: datetime

class ProductBatchResponse(ProductBatchCreate):
    id: int
    model_config = {"from_attributes": True}

# --- INVENTORY RECEIVE SCHEMAS ---
class InventoryReceive(BaseModel):
    product_id: int
    bin_id: int
    qty: float
    batch_id: Optional[int] = None

class InventoryResponse(BaseModel):
    id: int
    product_id: int
    batch_id: Optional[int]
    bin_id: int
    qty_available: float
    qty_reserved: float

    cross_dock_message: Optional[str] = None
    model_config = {"from_attributes": True}