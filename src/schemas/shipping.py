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

class ScanToShipRequest(BaseModel):
    order_id_barcode: str     # Scanned from the packing slip
    tracking_barcode: str     # Scanned from the FedEx sticker
    carrier: str = "FedEx"    # Selected on the scanner gun
    actual_weight_kg: float = 0.0