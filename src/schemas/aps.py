# src/schemas/aps.py
from pydantic import BaseModel
from typing import List

class ProductMetricsCreate(BaseModel):
    product_id: int
    avg_daily_demand: float
    demand_std_dev: float
    lead_time_days: int
    service_level_z_score: float = 1.65

class ReplenishmentRecommendation(BaseModel):
    product_id: int
    current_stock: float
    reorder_point: float
    suggested_order_qty: float
    action_taken: str