# src/schemas/billing.py
from pydantic import BaseModel
from typing import List
from datetime import datetime
from enum import Enum

class InvoiceStatusSchema(str, Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"

class InvoiceItemResponse(BaseModel):
    product_id: int
    qty: float
    unit_base_price: float
    tax_amount: float
    line_total: float
    model_config = {"from_attributes": True}

class InvoiceResponse(BaseModel):
    id: int
    order_id: int
    invoice_number: str
    subtotal: float
    tax_total: float
    grand_total: float
    currency: str
    status: InvoiceStatusSchema
    created_at: datetime
    items: List[InvoiceItemResponse]
    model_config = {"from_attributes": True}