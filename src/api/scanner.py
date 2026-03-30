# src/api/scanner.py
import json
import os
import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.core.database import SessionLocal
# Assuming standard model names based on your structure
from src.models.product import Product
from src.models.inventory import Inventory

router = APIRouter(prefix="/scanner", tags=["Barcode Scanning"])

# --- Database Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Safely Initialize Redis Client for WebSockets ---
_raw_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(' \'"\r\n')
_redis_kwargs = {}
if _raw_redis_url.startswith("rediss://"):
    _redis_kwargs["ssl_cert_reqs"] = "none"

redis_client = redis.Redis.from_url(_raw_redis_url, **_redis_kwargs)


# --- Pydantic Schemas for the Scanner Payload ---
class ScanReceivePayload(BaseModel):
    barcode: str
    location_id: int
    quantity: float = 1.0

class ScanPickPayload(BaseModel):
    barcode: str
    location_id: int
    order_id: int
    quantity: float = 1.0


# --- 1. LOOKUP ENDPOINT ---
@router.get("/lookup/{barcode}")
def lookup_barcode(barcode: str, db: Session = Depends(get_db)):
    """Scan a barcode to find out what the product is and where it is located."""
    # We assume 'sku' or 'upc' acts as the barcode. Adjust if your column is named differently!
    product = db.query(Product).filter(Product.sku == barcode).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Barcode not found in system.")
        
    inventory = db.query(Inventory).filter(Inventory.product_id == product.id).all()
    total_qty = sum(item.quantity for item in inventory)
    
    return {
        "status": "success",
        "product_id": product.id,
        "name": product.name,
        "sku": product.sku,
        "total_available": total_qty,
        "locations": [{"location_id": i.location_id, "quantity": i.quantity} for i in inventory]
    }


# --- 2. RECEIVE ENDPOINT ---
@router.post("/receive")
def receive_item(payload: ScanReceivePayload, db: Session = Depends(get_db)):
    """Scan an item as it comes off the truck to add it to inventory."""
    product = db.query(Product).filter(Product.sku == payload.barcode).first()
    if not product:
        raise HTTPException(status_code=404, detail="Unknown barcode scanned.")

    # Find if it already exists in this location
    inv_record = db.query(Inventory).filter(
        Inventory.product_id == product.id,
        Inventory.location_id == payload.location_id
    ).first()

    if inv_record:
        inv_record.quantity += payload.quantity
    else:
        # Create new inventory record
        inv_record = Inventory(
            product_id=product.id, 
            location_id=payload.location_id, 
            quantity=payload.quantity
        )
        db.add(inv_record)
        
    db.commit()

    # 🎉 Broadcast the scan to the WebSockets!
    alert = {
        "type": "SCAN_RECEIVE",
        "message": f"INBOUND: Received {payload.quantity}x of {product.name} at Location {payload.location_id}."
    }
    redis_client.publish("erp_notifications", json.dumps(alert))

    return {"status": "success", "message": alert["message"]}


# --- 3. PICK ENDPOINT ---
@router.post("/pick")
def pick_item(payload: ScanPickPayload, db: Session = Depends(get_db)):
    """Scan an item to deduct it from inventory and pack it for an order."""
    product = db.query(Product).filter(Product.sku == payload.barcode).first()
    if not product:
        raise HTTPException(status_code=404, detail="Unknown barcode scanned.")

    inv_record = db.query(Inventory).filter(
        Inventory.product_id == product.id,
        Inventory.location_id == payload.location_id
    ).first()

    if not inv_record or inv_record.quantity < payload.quantity:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient stock at Location {payload.location_id}. Scan failed."
        )

    # Deduct the inventory
    inv_record.quantity -= payload.quantity
    db.commit()

    # 🎉 Broadcast the pick to the WebSockets!
    alert = {
        "type": "SCAN_PICK",
        "message": f"OUTBOUND: Picked {payload.quantity}x of {product.name} for Order #{payload.order_id}."
    }
    redis_client.publish("erp_notifications", json.dumps(alert))

    return {"status": "success", "message": alert["message"]}