# src/schemas/order.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class OrderStatusSchema(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    BACKORDERED = "BACKORDERED" # <--- NEW

class OrderItemCreate(BaseModel):
    product_id: int
    qty: float

class OrderCreate(BaseModel):
    customer_name: str
    items: List[OrderItemCreate]

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    qty_ordered: float
    qty_allocated: float   # <--- NEW
    qty_backordered: float # <--- NEW
    model_config = {"from_attributes": True}

class OrderResponse(BaseModel):
    id: int
    customer_name: str
    status: OrderStatusSchema
    source: Optional[str] = "MANUAL_ENTRY"
    external_reference: Optional[str] = None
    items: List[OrderItemResponse]
    model_config = {"from_attributes": True}