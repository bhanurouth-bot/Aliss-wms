# src/api/shipping.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models.shipping import Shipment
from src.models.order import Order, OrderStatus
from src.schemas import shipping as schemas

# Import our new Celery task
from src.worker.tasks import send_shipping_webhook

router = APIRouter(prefix="/shipping", tags=["Dispatch & Fulfillment"])

@router.post("/dispatch/{order_id}", response_model=schemas.ShipmentResponse, status_code=201)
def dispatch_order(order_id: int, shipment_in: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    """
    Marks an order as SHIPPED, records tracking info, and triggers 
    an outbound webhook to notify the sales channel (Amazon/Shopify).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    if order.status != OrderStatus.PROCESSING:
        raise HTTPException(status_code=400, detail="Order is not ready for dispatch. Is it picked yet?")
        
    # 1. Create the Shipment record
    db_shipment = Shipment(
        order_id=order.id,
        carrier=shipment_in.carrier,
        tracking_number=shipment_in.tracking_number,
        shipping_method=shipment_in.shipping_method
    )
    db.add(db_shipment)
    
    # 2. Update the Order Status
    order.status = OrderStatus.SHIPPED
    db.commit()
    db.refresh(db_shipment)
    
    # 3. Fire the Webhook to Amazon/Shopify!
    if order.external_reference:
        send_shipping_webhook.delay(
            external_reference=order.external_reference,
            carrier=db_shipment.carrier,
            tracking_number=db_shipment.tracking_number
        )
        
    return db_shipment