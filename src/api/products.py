# src/api/products.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import product as models
from src.schemas import product as schemas
from src.services.audit_svc import log_audit # <-- 1. Import the service

router = APIRouter(prefix="/products", tags=["Product Catalog"])

@router.post("/", response_model=schemas.ProductResponse, status_code=201)
def create_product(product_in: schemas.ProductCreate, db: Session = Depends(get_db)):
    
    existing = db.query(models.Product).filter(
        (models.Product.sku == product_in.sku) | 
        (models.Product.barcode == product_in.barcode)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="SKU or Barcode already exists.")
        
    # --- REVERSE CALCULATE BASE PRICE ---
    # Formula: Base Price = MRP / (1 + (GST / 100))
    calculated_base_price = product_in.mrp / (1 + (product_in.gst_percent / 100.0))
    
    # Convert Pydantic schema to dict and add the calculated base_price
    product_data = product_in.model_dump()
    product_data["base_price"] = round(calculated_base_price, 2)
    
    db_product = models.Product(**product_data)
    db.add(db_product)
    
    # If you still have the Audit Log active, don't forget to flush and log here!
    db.commit()
    db.refresh(db_product)
    
    return db_product

@router.get("/", response_model=list[schemas.ProductResponse])
def list_products(db: Session = Depends(get_db)):
    """Get the full product catalog."""
    return db.query(models.Product).all()