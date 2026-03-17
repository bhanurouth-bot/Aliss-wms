# src/api/products.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import product as models
from src.schemas import product as schemas
from src.core.security import get_current_user
from src.models.auth import User
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
        
    # --- AUTO-CALCULATION REMOVED ---
    # We now trust the base_price passed in the JSON payload
    product_data = product_in.model_dump(exclude={"components"})
    
    db_product = Product(**product_data)
    db.add(db_product)
    db.flush() # Get the Product ID immediately!
    
    # SAVE THE BILL OF MATERIALS
    if product_in.is_kit and product_in.components:
        for comp in product_in.components:
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

@router.put("/discounts/category/{category_name}")
def bulk_update_category_discount(
    category_name: str, 
    discount_percent: float, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Applies a sale discount to an entire category of products."""
    products = db.query(Product).filter(Product.category == category_name).all()
    if not products:
        raise HTTPException(status_code=404, detail=f"No products found in category '{category_name}'.")
        
    for p in products:
        p.discount_percent = discount_percent
        
    db.commit()
    return {"message": f"Successfully applied {discount_percent}% discount to {len(products)} products in {category_name}."}


@router.put("/discounts/sku/{sku}")
def update_single_product_discount(
    sku: str, 
    discount_percent: float, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Applies a sale discount to a specific product."""
    product = db.query(Product).filter(Product.sku == sku).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
        
    product.discount_percent = discount_percent
    db.commit()
    return {"message": f"Successfully applied {discount_percent}% discount to SKU {sku}."}