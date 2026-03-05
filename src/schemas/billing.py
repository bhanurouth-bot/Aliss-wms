# src/schemas/billing.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

class InvoiceStatusSchema(str, Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"

class InvoiceItemResponse(BaseModel):
    id: int
    product_id: int
    qty: float
    unit_price: float
    tax_amount: float
    line_total: float
    model_config = {"from_attributes": True}

class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    order_id: int
    subtotal: float
    tax_total: float
    discount_total: float
    grand_total: float
    status: str
    created_at: datetime
    due_date: Optional[datetime]
    
    items: List[InvoiceItemResponse]
    model_config = {"from_attributes": True}