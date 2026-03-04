# src/api/rma.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from src.core.database import get_db
from src.core.security import require_role
from src.schemas import rma as schemas
from src.models.rma import RMA, RMAItem, RmaStatus, ItemCondition
from src.models.order import Order
from src.models.inventory import Inventory

router = APIRouter(prefix="/rma", tags=["Returns & Reverse Logistics (RMA)"])

@router.post("/", response_model=schemas.RMAResponse, status_code=201)
def create_rma(rma_in: schemas.RMACreate, db: Session = Depends(get_db)):
    """Customer Support creates an RMA when a customer wants to return an order."""
    
    order = db.query(Order).filter(Order.id == rma_in.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    rma_number = f"RMA-{datetime.now().strftime('%Y%m')}-{order.id:04d}"
    
    db_rma = RMA(order_id=order.id, rma_number=rma_number, reason=rma_in.reason)
    db.add(db_rma)
    db.flush()
    
    for item in rma_in.items:
        db_item = RMAItem(rma_id=db_rma.id, product_id=item.product_id, qty_returned=item.qty_returned)
        db.add(db_item)
        
    db.commit()
    db.refresh(db_rma)
    return db_rma

@router.post("/{rma_id}/inspect", response_model=schemas.RMAResponse)
def inspect_and_receive_rma(
    rma_id: int, 
    inspections: List[schemas.RMAItemInspect],
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    Warehouse Worker scans the returned box, inspects the items, and dictates 
    whether they go back to inventory (SELLABLE) or to the trash (DAMAGED).
    """
    rma = db.query(RMA).filter(RMA.id == rma_id).first()
    if not rma:
        raise HTTPException(status_code=404, detail="RMA not found")
        
    if rma.status == RmaStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="RMA is already completed.")

    for inspection in inspections:
        item = db.query(RMAItem).filter(RMAItem.id == inspection.rma_item_id, RMAItem.rma_id == rma.id).first()
        if not item:
            continue
            
        item.condition = ItemCondition(inspection.condition.value)
        
        # --- INVENTORY RECOVERY LOGIC ---
        if item.condition == ItemCondition.SELLABLE:
            if not inspection.bin_id:
                raise HTTPException(status_code=400, detail=f"Item {item.id} is SELLABLE. You must provide a bin_id to restock it.")
                
            # Put the item back on the shelf!
            inv_record = db.query(Inventory).filter(
                Inventory.product_id == item.product_id,
                Inventory.bin_id == inspection.bin_id
            ).first()
            
            if inv_record:
                inv_record.qty_available += item.qty_returned
            else:
                new_inv = Inventory(product_id=item.product_id, bin_id=inspection.bin_id, qty_available=item.qty_returned)
                db.add(new_inv)
                
        # If it's DAMAGED, we do absolutely nothing to inventory. We eat the loss.

    rma.status = RmaStatus.COMPLETED
    db.commit()
    db.refresh(rma)
    
    return rma