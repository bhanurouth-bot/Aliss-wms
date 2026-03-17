# src/schemas/order.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

# 🐛 BUG FIX: Perfectly align this Enum with src/models/order.py
class OrderStatusSchema(str, Enum):
    PENDING = "PENDING"           # 1. Order Placed
    IN_PROCESS = "IN_PROCESS"     # 2. Wave Generated
    CHECKING = "CHECKING"         # 3. Pick Scanned/Completed
    PACKING = "PACKING"           # 4. Checked & Bill Printed
    PACKED = "PACKED"             # 5. Box taped and labeled
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    BACKORDERED = "BACKORDERED"

class OrderItemCreate(BaseModel):
    product_id: int
    qty: float

class OrderCreate(BaseModel):
    customer_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    
    order_type: str = "B2C" # "B2B" or "B2C"
    route: Optional[str] = None
    items: List[OrderItemCreate]

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    qty_ordered: float
    qty_allocated: float
    qty_backordered: float
    model_config = {"from_attributes": True}

class OrderResponse(BaseModel):
    id: int
    customer_name: str
    status: OrderStatusSchema
    source: Optional[str] = "MANUAL_ENTRY"
    external_reference: Optional[str] = None
    items: List[OrderItemResponse]
    model_config = {"from_attributes": True}