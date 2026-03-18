# src/api/shipping.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from src.services.pdf_svc import generate_shipping_label_pdf

from src.core.database import get_db
from src.core.security import require_role

from src.models.order import Order, OrderStatus
from src.models.shipping import ShippingManifest

from src.schemas import shipping as schemas
from src.schemas.shipping import ScanToShipRequest

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

    # 2. Check if this specific order was already shipped
    existing = db.query(ShippingManifest).filter(ShippingManifest.order_id == order.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order has already been dispatched.")

    # --- NEW: Catch Duplicate Tracking Numbers to prevent 500 error! ---
    duplicate_tracking = db.query(ShippingManifest).filter(ShippingManifest.tracking_number == dispatch_data.tracking_number).first()
    if duplicate_tracking:
        raise HTTPException(
            status_code=409, # HTTP 409 means "Conflict" (Duplicate Data)
            detail=f"Tracking number '{dispatch_data.tracking_number}' is already assigned to Order #{duplicate_tracking.order_id}."
        )
    # -------------------------------------------------------------------

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
    reference_id = order.external_reference or str(order.id)
    send_shipping_webhook.delay(
        external_reference=reference_id,
        carrier=manifest.carrier,
        tracking_number=manifest.tracking_number
    )

    return manifest

@router.get("/label/{order_id}/pdf")
def download_shipping_label_pdf(
    order_id: int,
    carrier: str = "FEDEX",  # <--- NEW: Accepts a query parameter, defaults to FEDEX
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager", "Dock Worker"]))
):
    """Generates a 4x6 printable thermal shipping label."""
    # Pass the chosen carrier into the generator
    pdf_buffer, tracking_number = generate_shipping_label_pdf(db, order_id, carrier)
    
    headers = {
        "Content-Disposition": f"attachment; filename=LABEL-{tracking_number}.pdf"
    }
    
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers=headers
    )


@router.post("/scan-to-ship", response_model=schemas.ShippingManifestResponse)
def scan_to_ship_gate(
    payload: ScanToShipRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Dock Worker"]))
):
    """
    High-speed scanner endpoint. The worker shoots the Order barcode, 
    shoots the Tracking Label barcode, and the box is instantly dispatched.
    """
    order_id_str = payload.order_id_barcode.strip().replace("ORD-", "")
    tracking_clean = payload.tracking_barcode.strip()
    
    try:
        order_id = int(order_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Order Barcode format.")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    if order.status == OrderStatus.SHIPPED:
        raise HTTPException(status_code=400, detail="STOP! This order has already been shipped.")
        
    if order.status != OrderStatus.PACKED:
        raise HTTPException(status_code=400, detail=f"STOP! Order is currently {order.status.name}. It must be PACKED first.")

    # --- NEW: Catch Duplicate Tracking Numbers to prevent 500 error! ---
    duplicate_tracking = db.query(ShippingManifest).filter(ShippingManifest.tracking_number == tracking_clean).first()
    if duplicate_tracking:
        raise HTTPException(
            status_code=409, # 409 Conflict
            detail=f"Barcode Error: Tracking '{tracking_clean}' is already assigned to Order #{duplicate_tracking.order_id}!"
        )
    # -------------------------------------------------------------------

    # Create the Manifest
    manifest = ShippingManifest(
        order_id=order.id,
        carrier=payload.carrier,
        tracking_number=tracking_clean,
        actual_weight_kg=payload.actual_weight_kg,
        shipping_cost=0.0 
    )
    db.add(manifest)

    # Dispatch it!
    order.status = OrderStatus.SHIPPED
    
    db.commit()
    db.refresh(manifest)
    
    # Optional Webhook Trigger
    reference_id = order.external_reference or str(order.id)
    send_shipping_webhook.delay(
        external_reference=reference_id,
        carrier=manifest.carrier,
        tracking_number=manifest.tracking_number
    )
    
    return manifest