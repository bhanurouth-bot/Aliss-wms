# src/schemas/purchasing.py
from pydantic import BaseModel

class BackorderReportItem(BaseModel):
    product_id: int
    sku: str
    product_name: str
    total_backordered: float
    
    model_config = {"from_attributes": True}