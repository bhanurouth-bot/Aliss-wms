# src/schemas/manufacturing.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class ProductionStatusSchema(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

# --- BOM SCHEMAS ---
class BOMItemCreate(BaseModel):
    component_product_id: int
    qty_required: float

class BOMCreate(BaseModel):
    product_id: int
    name: str
    items: List[BOMItemCreate]

class BOMItemResponse(BaseModel):
    id: int
    component_product_id: int
    qty_required: float
    model_config = {"from_attributes": True}

class BOMResponse(BaseModel):
    id: int
    product_id: int
    name: str
    version: str
    items: List[BOMItemResponse]
    model_config = {"from_attributes": True}

# --- PRODUCTION ORDER SCHEMAS ---
class ProductionOrderCreate(BaseModel):
    bom_id: int
    qty_to_produce: float
    destination_bin_id: int

class ProductionOrderResponse(BaseModel):
    id: int
    bom_id: int
    status: ProductionStatusSchema
    qty_to_produce: float
    produced_batch_id: Optional[int]
    destination_bin_id: int
    model_config = {"from_attributes": True}