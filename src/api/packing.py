# src/api/packing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from src.core.database import get_db
from src.core.security import require_role
from src.models.order import Order, OrderStatus
from src.models.product import Product

router = APIRouter(prefix="/packing", tags=["Packing & Verification"])

# Schemas strictly for the packing station
class ScannedItem(BaseModel):
    barcode: str
    qty_scanned: float

class PackVerificationRequest(BaseModel):
    scanned_items: List[ScannedItem]

@router.post("/{order_id}/verify")
def verify_and_pack_order(
    order_id: int, 
    payload: PackVerificationRequest, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    The Checking Point: Compares what the packer physically scanned 
    against what the ERP expects for this order.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.status != OrderStatus.PICKED:
        raise HTTPException(
            status_code=400, 
            detail=f"Order is not ready for packing. Current status: {order.status.name}"
        )

    # 1. Aggregate what the packer scanned by barcode
    scanned_totals = {}
    for item in payload.scanned_items:
        scanned_totals[item.barcode] = scanned_totals.get(item.barcode, 0) + item.qty_scanned

    # 2. Compare against what is allocated in the Order
    for order_item in order.items:
        # We only care about what was successfully allocated (skip backordered items!)
        if order_item.qty_allocated <= 0:
            continue 
            
        product = db.query(Product).filter(Product.id == order_item.product_id).first()
        expected_qty = order_item.qty_allocated
        actual_scanned_qty = scanned_totals.get(product.barcode, 0)
        
        if actual_scanned_qty < expected_qty:
            raise HTTPException(
                status_code=400, 
                detail=f"Verification Failed! Missing items for {product.name}. Expected {expected_qty}, Scanned {actual_scanned_qty}."
            )
        elif actual_scanned_qty > expected_qty:
            raise HTTPException(
                status_code=400, 
                detail=f"Verification Failed! Too many items for {product.name}. Expected {expected_qty}, Scanned {actual_scanned_qty}. Remove the extra items!"
            )
            
        # If it matches, remove it from our tracking dictionary to check for completely wrong items next
        scanned_totals.pop(product.barcode, None)

    # 3. Did they scan something that doesn't belong in this box at all?
    if scanned_totals:
        wrong_barcodes = list(scanned_totals.keys())
        raise HTTPException(
            status_code=400, 
            detail=f"Verification Failed! You scanned items that do not belong in this order: {wrong_barcodes}"
        )

    # 4. Success! Tape the box shut.
    order.status = OrderStatus.PACKED
    db.commit()
    
    return {
        "message": "Verification Successful. All items match perfectly. Box is PACKED and ready for shipping label.",
        "order_id": order.id,
        "status": order.status.name
    }