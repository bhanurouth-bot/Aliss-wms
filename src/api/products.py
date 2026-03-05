# src/api/products.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import product as models
from src.schemas import product as schemas
from src.core.security import get_current_user
from src.models.auth import User
from src.services.audit_svc import log_activity
from src.models.product import Product, KitComponent

router = APIRouter(prefix="/products", tags=["Product Catalog"])

@router.post("/", response_model=schemas.ProductResponse, status_code=201)
def create_product(
    product_in: schemas.ProductCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    existing = db.query(Product).filter(
        (Product.sku == product_in.sku) | (Product.barcode == product_in.barcode)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="SKU or Barcode already exists.")
        
    calculated_base_price = product_in.mrp / (1 + (product_in.gst_percent / 100.0))
    
    # Exclude components from the initial dictionary dump
    product_data = product_in.model_dump(exclude={"components"})
    product_data["base_price"] = round(calculated_base_price, 2)
    
    db_product = Product(**product_data)
    db.add(db_product)
    db.flush() # Get the Product ID immediately!
    
    # --- NEW: SAVE THE BILL OF MATERIALS ---
    if product_in.is_kit and product_in.components:
        for comp in product_in.components:
            # Verify the component actually exists
            child_product = db.query(Product).filter(Product.id == comp.component_id).first()
            if not child_product:
                raise HTTPException(status_code=400, detail=f"Component ID {comp.component_id} does not exist.")
                
            db_kit_comp = KitComponent(
                kit_id=db_product.id,
                component_id=comp.component_id,
                qty=comp.qty
            )
            db.add(db_kit_comp)

    db.commit()
    db.refresh(db_product)
    
    return db_product

@router.get("/", response_model=list[schemas.ProductResponse])
def list_products(db: Session = Depends(get_db)):
    """Get the full product catalog."""
    return db.query(models.Product).all()