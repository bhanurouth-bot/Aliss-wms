# src/schemas/shipping.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from src.models.shipping import DeliveryStatus

class ShippingDispatchCreate(BaseModel):
    carrier: str
    tracking_number: str
    actual_weight_kg: float
    shipping_cost: Optional[float] = 0.0

class ShippingManifestResponse(BaseModel):
    id: int
    order_id: int
    carrier: str
    tracking_number: str
    actual_weight_kg: float
    shipping_cost: float
    status: DeliveryStatus
    dispatched_at: datetime
    
    model_config = {"from_attributes": True}