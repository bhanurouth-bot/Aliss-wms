# src/models/manufacturing.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum
from src.core.database import Base

class ProductionStatus(enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class BillOfMaterial(Base):
    """The 'Recipe' for a finished product."""
    __tablename__ = 'boms'
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), unique=True) # The Finished Good
    name = Column(String)
    version = Column(String, default="v1.0")
    
    items = relationship("BOMItem", back_populates="bom", cascade="all, delete-orphan")

class BOMItem(Base):
    """The raw materials needed for the recipe."""
    __tablename__ = 'bom_items'
    id = Column(Integer, primary_key=True, index=True)
    bom_id = Column(Integer, ForeignKey('boms.id'))
    component_product_id = Column(Integer, ForeignKey('products.id')) # The Raw Material
    qty_required = Column(Float) # Qty needed to make exactly ONE finished good
    
    bom = relationship("BillOfMaterial", back_populates="items")

class ProductionOrder(Base):
    """A ticket to actually manufacture a batch of goods."""
    __tablename__ = 'production_orders'
    id = Column(Integer, primary_key=True, index=True)
    bom_id = Column(Integer, ForeignKey('boms.id'))
    status = Column(SQLEnum(ProductionStatus), default=ProductionStatus.PLANNED)
    
    qty_to_produce = Column(Float)
    produced_batch_id = Column(Integer, ForeignKey('product_batches.id'), nullable=True)
    
    # Where should the finished goods be placed when done?
    destination_bin_id = Column(Integer, ForeignKey('bins.id'))