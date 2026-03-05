# src/api/inventory.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import inventory as inv_models
from src.models import product as prod_models
from src.models import wms as wms_models
from src.schemas import inventory as schemas
from src.services.order_svc import auto_cross_dock


router = APIRouter(prefix="/inventory", tags=["Inventory & Stock"])

@router.post("/batches/", response_model=schemas.ProductBatchResponse, status_code=201)
def create_batch(batch_in: schemas.ProductBatchCreate, db: Session = Depends(get_db)):
    """Register a new batch/expiry date for a product."""
    
    # Check if batch number already exists
    existing = db.query(inv_models.ProductBatch).filter(
        inv_models.ProductBatch.batch_number == batch_in.batch_number
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Batch number already exists.")
        
    db_batch = inv_models.ProductBatch(**batch_in.model_dump())
    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)
    return db_batch

@router.post("/receive/", response_model=schemas.InventoryResponse)
def receive_goods(receipt_in: schemas.InventoryReceive, db: Session = Depends(get_db)):
    """Add stock to a specific bin and check for Cross-Docking opportunities."""
    
    # 1. Validate Product and Bin
    product = db.query(prod_models.Product).filter(prod_models.Product.id == receipt_in.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
        
    bin_record = db.query(wms_models.Bin).filter(wms_models.Bin.id == receipt_in.bin_id).first()
    if not bin_record:
        raise HTTPException(status_code=404, detail="Bin not found.")

    if product.requires_batch_tracking and not receipt_in.batch_id:
        raise HTTPException(status_code=400, detail=f"Product {product.sku} requires a batch_id.")
        
    # 2. Record the Inventory
    inventory = db.query(inv_models.Inventory).filter(
        inv_models.Inventory.product_id == receipt_in.product_id,
        inv_models.Inventory.bin_id == receipt_in.bin_id,
        inv_models.Inventory.batch_id == receipt_in.batch_id
    ).first()

    if inventory:
        inventory.qty_available += receipt_in.qty
    else:
        inventory = inv_models.Inventory(
            product_id=receipt_in.product_id,
            bin_id=receipt_in.bin_id,
            batch_id=receipt_in.batch_id,
            qty_available=receipt_in.qty
        )
        db.add(inventory)
        
    db.commit()
    db.refresh(inventory)
    
    # --- 3. THE CROSS-DOCK TRIGGER ---
    cross_docked_orders = auto_cross_dock(db, product_id=receipt_in.product_id)
    
    if cross_docked_orders:
        db.refresh(inventory) # Refresh inventory since the cross-dock engine just reserved some of it!
        
        # We attach a dynamic attribute to the SQLAlchemy model so Pydantic picks it up
        setattr(inventory, "cross_dock_message", 
                f"🚨 CROSS-DOCK ALERT! Stock immediately routed to fulfill Orders: {cross_docked_orders}. Skip put-away and take items directly to Packing Desk!")

    return inventory

@router.get("/", response_model=list[schemas.InventoryResponse])
def get_all_inventory(db: Session = Depends(get_db)):
    """View all stock across all bins."""
    return db.query(inv_models.Inventory).all()