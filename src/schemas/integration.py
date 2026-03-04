# src/schemas/integration.py
from pydantic import BaseModel
from typing import List

class InboundOrderItem(BaseModel):
    sku: str
    qty: float

class InboundOrderPayload(BaseModel):
    source: str                 # e.g., "SHOPIFY", "AMAZON"
    external_reference: str     # The Order ID from the website
    customer_name: str
    items: List[InboundOrderItem]