# src/schemas/purchasing.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# --- PO Schemas ---
class POItemCreate(BaseModel):
    product_id: int
    qty_ordered: float
    unit_cost: float

class POCreate(BaseModel):
    supplier_id: int
    items: List[POItemCreate]

class POItemResponse(BaseModel):
    id: int
    product_id: int
    qty_ordered: float
    qty_received: float
    unit_cost: float
    model_config = {"from_attributes": True}

class POResponse(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    status: str
    created_at: datetime
    items: List[POItemResponse]
    model_config = {"from_attributes": True}

# --- Receiving Dock / GRN Schemas ---
class GRNItemScan(BaseModel):
    product_id: int
    qty_received: float
    bin_id: int
    batch_id: Optional[int] = None

class GRNCreateRequest(BaseModel):
    notes: Optional[str] = "Delivery arrived via FedEx"
    scanned_items: List[GRNItemScan]

class CatalogItemCreate(BaseModel):
    product_id: int
    negotiated_unit_cost: float
    minimum_order_qty: float = 1.0
    lead_time_days: int = 7
    is_primary: bool = True

class CatalogItemResponse(CatalogItemCreate):
    id: int
    supplier_id: int
    model_config = {"from_attributes": True}