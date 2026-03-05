# src/api/transfers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from src.core.database import get_db
from src.core.security import require_role
from src.schemas import transfer as schemas
from src.models.transfer import TransferOrder, TransferOrderItem, TransferStatus
from src.models.inventory import Inventory

router = APIRouter(prefix="/transfers", tags=["Inter-Warehouse Transfers (IWT)"])

@router.post("/", response_model=schemas.TransferResponse, status_code=201)
def create_transfer_order(
    payload: schemas.TransferCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager"]))
):
    """Drafts a new Inter-Warehouse Transfer."""
    transfer_number = f"TRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    db_transfer = TransferOrder(
        transfer_number=transfer_number,
        source_warehouse_id=payload.source_warehouse_id,
        destination_warehouse_id=payload.destination_warehouse_id
    )
    db.add(db_transfer)
    db.flush()
    
    for item in payload.items:
        db_item = TransferOrderItem(
            transfer_order_id=db_transfer.id,
            product_id=item.product_id,
            qty_requested=item.qty
        )
        db.add(db_item)
        
    db.commit()
    db.refresh(db_transfer)
    return db_transfer

@router.post("/{transfer_id}/dispatch", response_model=schemas.TransferResponse)
def dispatch_transfer(
    transfer_id: int, 
    payload: schemas.TransferActionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    Source Warehouse: Loads the truck. Deducts inventory from the source bins 
    and sets status to IN_TRANSIT.
    """
    transfer = db.query(TransferOrder).filter(TransferOrder.id == transfer_id).first()
    if not transfer or transfer.status != TransferStatus.PENDING:
        raise HTTPException(status_code=400, detail="Transfer not found or not in PENDING status.")

    for action in payload.items:
        # Deduct from Source Warehouse Bin
        inv_record = db.query(Inventory).filter(
            Inventory.product_id == action.product_id,
            Inventory.bin_id == action.bin_id,
            Inventory.batch_id == action.batch_id
        ).with_for_update().first()
        
        if not inv_record or inv_record.qty_available < action.qty:
            raise HTTPException(status_code=400, detail=f"Insufficient stock in Source Bin {action.bin_id}")
            
        inv_record.qty_available -= action.qty
        
        # Update the Transfer Item
        t_item = db.query(TransferOrderItem).filter(
            TransferOrderItem.transfer_order_id == transfer.id,
            TransferOrderItem.product_id == action.product_id
        ).first()
        if t_item:
            t_item.qty_shipped += action.qty

    transfer.status = TransferStatus.IN_TRANSIT
    transfer.shipped_at = datetime.now()
    db.commit()
    db.refresh(transfer)
    return transfer

@router.post("/{transfer_id}/receive", response_model=schemas.TransferResponse)
def receive_transfer(
    transfer_id: int, 
    payload: schemas.TransferActionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    """
    Destination Warehouse: Unloads the truck. Adds inventory to the destination bins 
    and sets status to COMPLETED.
    """
    transfer = db.query(TransferOrder).filter(TransferOrder.id == transfer_id).first()
    if not transfer or transfer.status != TransferStatus.IN_TRANSIT:
        raise HTTPException(status_code=400, detail="Transfer not found or not IN_TRANSIT.")

    for action in payload.items:
        # Add to Destination Warehouse Bin
        inv_record = db.query(Inventory).filter(
            Inventory.product_id == action.product_id,
            Inventory.bin_id == action.bin_id,
            Inventory.batch_id == action.batch_id
        ).first()
        
        if inv_record:
            inv_record.qty_available += action.qty
        else:
            new_inv = Inventory(
                product_id=action.product_id,
                bin_id=action.bin_id,
                batch_id=action.batch_id,
                qty_available=action.qty
            )
            db.add(new_inv)
            
        # Update the Transfer Item
        t_item = db.query(TransferOrderItem).filter(
            TransferOrderItem.transfer_order_id == transfer.id,
            TransferOrderItem.product_id == action.product_id
        ).first()
        if t_item:
            t_item.qty_received += action.qty

    transfer.status = TransferStatus.COMPLETED
    transfer.received_at = datetime.now()
    db.commit()
    db.refresh(transfer)
    return transfer