# src/api/purchasing.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from src.core.database import get_db
from src.core.security import require_role
from src.schemas import purchasing as schemas

from src.models.product import Product
from src.models.order import Order, OrderItem, OrderStatus

router = APIRouter(prefix="/purchasing", tags=["Purchasing & Procurement"])

@router.get("/reports/backorders", response_model=List[schemas.BackorderReportItem])
def get_aggregated_backorders(
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Purchasing"])) # Locked down!
):
    """
    Generates a live 'Shopping List' for the Procurement team.
    Sums up all missing stock across every active backordered sales order.
    """
    
    # We use SQLAlchemy's .label() to map the SQL columns directly to our Pydantic schema
    results = (
        db.query(
            Product.id.label("product_id"),
            Product.sku.label("sku"),
            Product.name.label("product_name"),
            func.sum(OrderItem.qty_backordered).label("total_backordered")
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        # Only count stock from orders that are actually backordered (ignore shipped/cancelled ones)
        .filter(Order.status == OrderStatus.BACKORDERED)
        .filter(OrderItem.qty_backordered > 0)
        .group_by(Product.id, Product.sku, Product.name)
        .all()
    )
    
    return results