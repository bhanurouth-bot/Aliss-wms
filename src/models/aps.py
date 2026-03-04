# src/models/aps.py
from sqlalchemy import Column, Integer, Float, ForeignKey
from src.core.database import Base

class ProductMetrics(Base):
    __tablename__ = 'aps_metrics'
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), unique=True)
    
    # Historical tracking
    avg_daily_demand = Column(Float, default=1.0)
    demand_std_dev = Column(Float, default=0.2)
    
    # Supplier constraints
    lead_time_days = Column(Integer, default=7)
    
    # Z-Score for desired Service Level (1.65 = 95% service level)
    service_level_z_score = Column(Float, default=1.65)