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
    """Source Warehouse: Deducts inventory and enforces dispatch limits."""
    transfer = db.query(TransferOrder).filter(TransferOrder.id == transfer_id).first()
    if not transfer or transfer.status != TransferStatus.PENDING:
        raise HTTPException(status_code=400, detail="Transfer not found or not in PENDING status.")

    for action in payload.items:
        # 1. Fetch the ledger item FIRST
        t_item = db.query(TransferOrderItem).filter(
            TransferOrderItem.transfer_order_id == transfer.id,
            TransferOrderItem.product_id == action.product_id
        ).first()
        
        if not t_item:
            raise HTTPException(status_code=400, detail=f"Product {action.product_id} is not part of this transfer.")
            
        # 2. VALIDATION: Prevent over-shipping!
        if t_item.qty_shipped + action.qty > t_item.qty_requested:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot dispatch {action.qty}. You are over-shipping! Only {t_item.qty_requested - t_item.qty_shipped} requested."
            )

        # 3. Deduct from Source Inventory safely
        inv_record = db.query(Inventory).filter(
            Inventory.product_id == action.product_id,
            Inventory.bin_id == action.bin_id,
            Inventory.batch_id == action.batch_id
        ).with_for_update().first()
        
        if not inv_record or inv_record.qty_available < action.qty:
            raise HTTPException(status_code=400, detail=f"Insufficient stock in Source Bin {action.bin_id}")
            
        inv_record.qty_available -= action.qty
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
    """Destination Warehouse: Adds inventory and prevents phantom receiving."""
    transfer = db.query(TransferOrder).filter(TransferOrder.id == transfer_id).first()
    if not transfer or transfer.status != TransferStatus.IN_TRANSIT:
        raise HTTPException(status_code=400, detail="Transfer not found or not IN_TRANSIT.")

    for action in payload.items:
        # 1. Fetch the ledger item FIRST
        t_item = db.query(TransferOrderItem).filter(
            TransferOrderItem.transfer_order_id == transfer.id,
            TransferOrderItem.product_id == action.product_id
        ).first()
        
        if not t_item:
            raise HTTPException(status_code=400, detail=f"Product {action.product_id} was never shipped on this transfer.")
            
        # 2. VALIDATION: Prevent phantom receiving!
        if t_item.qty_received + action.qty > t_item.qty_shipped:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot receive {action.qty}. The source warehouse only shipped {t_item.qty_shipped - t_item.qty_received} remaining units. Check the truck again!"
            )

        # 3. Add to Destination Inventory safely
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
            
        t_item.qty_received += action.qty

    transfer.status = TransferStatus.COMPLETED
    transfer.received_at = datetime.now()
    db.commit()
    db.refresh(transfer)
    return transfer