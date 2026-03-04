# src/schemas/shipping.py
from pydantic import BaseModel
from datetime import datetime

class ShipmentCreate(BaseModel):
    carrier: str
    tracking_number: str
    shipping_method: str

class ShipmentResponse(BaseModel):
    id: int
    order_id: int
    carrier: str
    tracking_number: str
    shipping_method: str
    shipped_at: datetime
    
    model_config = {"from_attributes": True}