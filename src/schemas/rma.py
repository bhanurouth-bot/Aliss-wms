# src/schemas/rma.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

class ItemConditionSchema(str, Enum):
    SELLABLE = "SELLABLE"
    DAMAGED = "DAMAGED"

class RMAItemCreate(BaseModel):
    product_id: int
    qty_returned: float

class RMACreate(BaseModel):
    order_id: int
    reason: str
    items: List[RMAItemCreate]

class RMAItemInspect(BaseModel):
    rma_item_id: int
    condition: ItemConditionSchema
    bin_id: Optional[int] = None # Where the worker put it (Required if SELLABLE)

class RMAResponse(BaseModel):
    id: int
    order_id: int
    rma_number: str
    status: str
    reason: str
    created_at: datetime
    model_config = {"from_attributes": True}