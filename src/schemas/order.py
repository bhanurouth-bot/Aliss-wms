# src/schemas/order.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class OrderStatusSchema(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING" # WMS is routing the picker
    PICKED = "PICKED"         # Sitting at the Packing Station
    PACKED = "PACKED"         # Verified, boxed, waiting for dispatch
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    BACKORDERED = "BACKORDERED"

class OrderItemCreate(BaseModel):
    product_id: int
    qty: float

class OrderCreate(BaseModel):
    customer_name: str
    order_type: str = "B2C" # "B2B" or "B2C"
    route: Optional[str] = None
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