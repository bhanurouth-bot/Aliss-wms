# src/schemas/billing.py
from pydantic import BaseModel, computed_field
from typing import List, Optional
from datetime import datetime
from enum import Enum

class InvoiceStatusSchema(str, Enum):
    DRAFT = "DRAFT"
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    VOID = "VOID"

class PaymentMethodSchema(str, Enum):
    CASH = "CASH"
    CREDIT_CARD = "CREDIT_CARD"
    WIRE_TRANSFER = "WIRE_TRANSFER"
    CHECK = "CHECK"
    ONLINE = "ONLINE"

# --- NEW: Payment Schemas ---
class PaymentCreate(BaseModel):
    amount: float
    payment_method: PaymentMethodSchema
    reference_number: Optional[str] = None

class PaymentResponse(BaseModel):
    id: int
    invoice_id: int
    amount: float
    payment_method: PaymentMethodSchema
    reference_number: Optional[str]
    payment_date: datetime
    model_config = {"from_attributes": True}

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
    amount_paid: float  # <--- NEW
    
    status: InvoiceStatusSchema
    created_at: datetime
    due_date: Optional[datetime]
    
    items: List[InvoiceItemResponse]
    payments: List[PaymentResponse] = [] # <--- NEW
    
    # <--- NEW: Automatically calculate Balance Due for the frontend!
    @computed_field
    def balance_due(self) -> float:
        return round(self.grand_total - self.amount_paid, 2)
        
    model_config = {"from_attributes": True}