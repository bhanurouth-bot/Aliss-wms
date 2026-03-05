# src/schemas/wms_ops.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class TaskStatusSchema(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class PickTaskResponse(BaseModel):
    id: int
    product_id: int
    bin_id: int
    batch_id: Optional[int]
    qty_expected: float
    qty_picked: float
    status: TaskStatusSchema
    
    model_config = {"from_attributes": True}

class PicklistResponse(BaseModel):
    id: int
    order_id: int
    status: TaskStatusSchema
    tasks: List[PickTaskResponse]
    
    model_config = {"from_attributes": True}

class PickConfirmation(BaseModel):
    scanned_bin_barcode: str
    scanned_product_barcode: str
    qty_picked: float

class PickTaskResponse(BaseModel):
    id: int
    product_id: int
    bin_id: int
    batch_id: Optional[int]
    qty_expected: float
    qty_picked: float
    status: str
    model_config = {"from_attributes": True}

class PickingWaveResponse(BaseModel):
    id: int
    wave_name: str
    status: str
    tasks: List[PickTaskResponse] = []
    model_config = {"from_attributes": True}