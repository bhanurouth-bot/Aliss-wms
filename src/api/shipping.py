# src/api/shipping.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.security import require_role

from src.models.order import Order, OrderStatus
from src.models.shipping import ShippingManifest
from src.schemas import shipping as schemas

# --- IMPORT THE CELERY TASK ---
from src.worker.tasks import send_shipping_webhook

router = APIRouter(prefix="/shipping", tags=["Shipping & Dispatch"])

@router.post("/dispatch/{order_id}", response_model=schemas.ShippingManifestResponse)
def dispatch_order(
    order_id: int, 
    dispatch_data: schemas.ShippingDispatchCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager", "Dock Worker"]))
):
    # 1. Verify the order is actually PACKED
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    if order.status != OrderStatus.PACKED:
        raise HTTPException(
            status_code=400, 
            detail=f"Order cannot be dispatched. Current status is {order.status.name}, expected PACKED."
        )

    # 2. Check if it was already shipped
    existing = db.query(ShippingManifest).filter(ShippingManifest.order_id == order.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order has already been dispatched.")

    # 3. Create the Shipping Manifest
    manifest = ShippingManifest(
        order_id=order.id,
        carrier=dispatch_data.carrier,
        tracking_number=dispatch_data.tracking_number,
        actual_weight_kg=dispatch_data.actual_weight_kg,
        shipping_cost=dispatch_data.shipping_cost
    )
    db.add(manifest)

    # 4. Final State Transition
    order.status = OrderStatus.SHIPPED
    
    db.commit()
    db.refresh(manifest)
    
    # 5. --- FIRE THE WEBHOOK IN THE BACKGROUND ---
    # We use order.external_reference (e.g., "AMZ-998877") so the external site knows which order this is.
    # If there is no external reference, we just send the internal ERP ID.
    reference_id = order.external_reference or str(order.id)
    
    send_shipping_webhook.delay(
        external_reference=reference_id,
        carrier=manifest.carrier,
        tracking_number=manifest.tracking_number
    )

    return manifest