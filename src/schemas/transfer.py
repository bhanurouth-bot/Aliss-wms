# src/schemas/transfer.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TransferItemCreate(BaseModel):
    product_id: int
    qty: float

class TransferCreate(BaseModel):
    source_warehouse_id: int
    destination_warehouse_id: int
    items: List[TransferItemCreate]

# Schemas for the physical execution
class TransferActionItem(BaseModel):
    product_id: int
    bin_id: int      # Where the worker took it from (or put it into)
    batch_id: Optional[int] = None
    qty: float

class TransferActionRequest(BaseModel):
    items: List[TransferActionItem]

class TransferResponse(BaseModel):
    id: int
    transfer_number: str
    source_warehouse_id: int
    destination_warehouse_id: int
    status: str
    model_config = {"from_attributes": True}