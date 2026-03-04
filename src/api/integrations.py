# src/api/integrations.py
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.schemas import integration as schemas
from src.schemas.order import OrderCreate, OrderItemCreate
from src.models.product import Product
from src.models.order import Order
from src.services.order_svc import create_order_with_fefo_reservation

router = APIRouter(prefix="/integrations", tags=["External Integrations & Webhooks"])

# Setup Server-to-Server API Key Security
API_KEY_NAME = "X-ERP-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verify_api_key(api_key: str = Security(api_key_header)):
    # In production, load this from your .env file!
    if api_key != "super_secret_amazon_shopify_key_2026":
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

@router.post("/webhooks/orders/inbound", status_code=201)
def receive_external_order(
    payload: schemas.InboundOrderPayload, 
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Webhook endpoint for Shopify, Amazon, etc., to push orders into the ERP."""
    
    # 1. Idempotency Check: Did we already receive this exact order?
    existing_order = db.query(Order).filter(Order.external_reference == payload.external_reference).first()
    if existing_order:
        return {"message": "Order already exists", "erp_order_id": existing_order.id}

    # 2. SKU to Product ID Translation
    internal_items = []
    for item in payload.items:
        product = db.query(Product).filter(Product.sku == item.sku).first()
        if not product:
            # If Amazon sells a SKU we don't have, we must reject the order (or flag it)
            raise HTTPException(status_code=400, detail=f"Unknown SKU from external source: {item.sku}")
            
        internal_items.append(
            OrderItemCreate(product_id=product.id, qty=item.qty)
        )

    # 3. Construct the internal Order Create schema
    internal_order_schema = OrderCreate(
        customer_name=payload.customer_name,
        items=internal_items
    )

    # 4. Pass to the FEFO Engine!
    try:
        # --- WE NOW ALLOW BACKORDERS FOR INTEGRATIONS ---
        db_order = create_order_with_fefo_reservation(
            db, 
            internal_order_schema, 
            allow_backorder=True 
        )
        
        db_order.source = payload.source
        db_order.external_reference = payload.external_reference
        db.commit()
        
        return {
            "message": "Order successfully ingested.",
            "erp_order_id": db_order.id,
            "status": db_order.status.name # Will be PENDING or BACKORDERED
        }
        
    except HTTPException as e:
        # If the FEFO engine throws an Insufficient Stock error, we pass it back to the website
        raise HTTPException(status_code=400, detail=f"Order ingestion failed: {e.detail}")