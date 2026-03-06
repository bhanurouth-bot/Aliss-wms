# src/models/order.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum
from src.core.database import Base

class OrderStatus(enum.Enum):
    PENDING = "PENDING"           # 1. Order Placed
    IN_PROCESS = "IN_PROCESS"     # 2. Wave Generated (PDF handed to picker)
    CHECKING = "CHECKING"         # 3. Pick Scanned/Completed (Waiting at QC desk)
    PACKING = "PACKING"           # 4. Checked & Bill Printed (Ready for a box)
    PACKED = "PACKED"             # 5. Box taped and labeled
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    BACKORDERED = "BACKORDERED"

class CustomerType(enum.Enum):
    B2C = "B2C" # Regular customer (Requires standard billing)
    B2B = "B2B" # Wholesale/Retailer (Requires bulk billing/invoicing)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    
    # --- NEW: SMART FILTERS ---
    order_type = Column(SQLEnum(CustomerType), default=CustomerType.B2C)
    is_single_sku = Column(Boolean, default=True) # Used to group fast-pack orders
    route = Column(String, nullable=True)         # e.g., "MORNING-DISPATCH", "FEDEX-EXPRESS"
    cutoff_time = Column(DateTime, nullable=True) # Must be packed before this time
    
    wave_id = Column(Integer, ForeignKey('picking_waves.id'), nullable=True) # Link to the bulk wave
    
    source = Column(String, default="MANUAL_ENTRY") 
    external_reference = Column(String, unique=True, nullable=True, index=True) 
    
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    packed_by = Column(Integer, ForeignKey('users.id'), nullable=True) # Who taped the box shut?
    packed_at = Column(DateTime(timezone=True), nullable=True)


class OrderItem(Base):
    __tablename__ = 'order_items'
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    
    qty_ordered = Column(Float)
    qty_allocated = Column(Float, default=0.0)   
    qty_backordered = Column(Float, default=0.0) 
    
    order = relationship("Order", back_populates="items")