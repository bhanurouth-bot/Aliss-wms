# src/models/order.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum
from src.core.database import Base

class OrderStatus(enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    BACKORDERED = "BACKORDERED" # <--- NEW STATUS

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    
    source = Column(String, default="MANUAL_ENTRY") 
    external_reference = Column(String, unique=True, nullable=True, index=True) 
    
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = 'order_items'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty_ordered = Column(Float)
    qty_allocated = Column(Float, default=0.0)   # <--- What we actually secured
    qty_backordered = Column(Float, default=0.0) # <--- What we are missing
    
    order = relationship("Order", back_populates="items")