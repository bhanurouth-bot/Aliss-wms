# src/schemas/cycle_count.py
from pydantic import BaseModel
from datetime import datetime

class CycleCountRequest(BaseModel):
    product_id: int
    bin_id: int
    physical_qty: float
    reason: str = "ROUTINE_CYCLE_COUNT"

class AdjustmentResponse(BaseModel):
    id: int
    inventory_id: int
    previous_qty: float
    new_qty: float
    variance: float
    reason: str
    created_at: datetime
    
    model_config = {"from_attributes": True}