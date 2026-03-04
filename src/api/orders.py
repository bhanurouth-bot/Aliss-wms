# src/api/orders.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.schemas import order as schemas
from src.services.order_svc import create_order_with_fefo_reservation
from src.models.order import Order

router = APIRouter(prefix="/orders", tags=["Sales Orders"])

@router.post("/", response_model=schemas.OrderResponse, status_code=201)
def create_sales_order(order_in: schemas.OrderCreate, db: Session = Depends(get_db)):
    """Create a new sales order and reserve stock."""
    return create_order_with_fefo_reservation(db, order_in)

@router.get("/", response_model=list[schemas.OrderResponse])
def list_orders(db: Session = Depends(get_db)):
    """List all orders."""
    return db.query(Order).all()