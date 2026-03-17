# src/schemas/sales.py
from pydantic import BaseModel
from typing import List

class CategoryCampaign(BaseModel):
    category_name: str
    discount_percent: float

class BrandCampaign(BaseModel):
    brand_name: str
    discount_percent: float

class ClearanceCampaign(BaseModel):
    skus: List[str]
    discount_percent: float