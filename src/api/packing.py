# src/api/packing.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from src.core.database import get_db
from src.core.security import require_role
from src.models.order import Order, OrderStatus
from src.models.product import Product
from src.models.wms import PackagingBox


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
    order.packed_by = current_user.id 
    order.packed_at = datetime.now()
    db.commit()
    
    return {
        "message": "Verification Successful. All items match perfectly. Box is PACKED and ready for shipping label.",
        "order_id": order.id,
        "status": order.status.name
    }

class BoxCreate(BaseModel):
    name: str
    length_cm: float
    width_cm: float
    height_cm: float
    max_weight_kg: float
    empty_weight_kg: float

@router.post("/boxes", status_code=201)
def create_packaging_box(
    payload: BoxCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager"]))
):
    """Registers a new standard shipping box size into the WMS."""
    box = PackagingBox(**payload.model_dump())
    db.add(box)
    db.commit()
    db.refresh(box)
    return box

@router.get("/{order_id}/cartonize")
def calculate_optimal_box(
    order_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    The Cartonization Engine: Calculates the 3D volume and total weight of 
    an order's items. If an item is a Kit, it dynamically explodes the kit 
    to calculate the volume of its inner components!
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    total_volume_cm3 = 0.0
    total_weight_kg = 0.0

    # 1. Calculate the physics of the items
    for item in order.items:
        if item.qty_allocated <= 0:
            continue
            
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        # --- NEW: KIT-AWARE CARTONIZATION ---
        if product.components: # If this product has inner components, it's a Kit!
            for kit_link in product.components:
                comp_prod = kit_link.component
                
                # Volume of the internal component
                comp_vol = comp_prod.length_cm * comp_prod.width_cm * comp_prod.height_cm
                
                # Multiply by (Qty of component in kit) * (Qty of kits ordered)
                total_qty = kit_link.qty * item.qty_allocated
                
                total_volume_cm3 += (comp_vol * total_qty)
                total_weight_kg += (comp_prod.weight_kg * total_qty)
                
        else:
            # Standard single product
            item_vol = product.length_cm * product.width_cm * product.height_cm
            total_volume_cm3 += (item_vol * item.qty_allocated)
            total_weight_kg += (product.weight_kg * item.qty_allocated)

    if total_volume_cm3 == 0:
        return {"message": "Items have no dimensions configured. Cannot calculate box size."}

    # 2. Find all boxes that can fit the volume AND hold the weight
    all_boxes = db.query(PackagingBox).all()
    valid_boxes = []
    
    for box in all_boxes:
        box_vol = box.length_cm * box.width_cm * box.height_cm
        if box_vol >= total_volume_cm3 and box.max_weight_kg >= total_weight_kg:
            valid_boxes.append({
                "box_id": box.id,
                "box_name": box.name,
                "box_volume": box_vol,
                "fill_percentage": round((total_volume_cm3 / box_vol) * 100, 2),
                "total_shipping_weight": round(total_weight_kg + box.empty_weight_kg, 2)
            })

    if not valid_boxes:
        raise HTTPException(
            status_code=400, 
            detail=f"No box is large/strong enough! Volume: {total_volume_cm3}cm3, Weight: {total_weight_kg}kg. Consider splitting the order into multiple shipments."
        )

    # 3. Sort by volume to find the tightest fit (cheapest shipping cost!)
    valid_boxes.sort(key=lambda x: x["box_volume"])
    
    best_box = valid_boxes[0]

    return {
        "message": "Cartonization successful.",
        "order_id": order_id,
        "items_volume_cm3": total_volume_cm3,
        "items_weight_kg": total_weight_kg,
        "recommended_box": best_box["box_name"],
        "estimated_fill_rate": f"{best_box['fill_percentage']}%",
        "final_shipping_weight_kg": best_box["total_shipping_weight"]
    }