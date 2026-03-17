# src/api/sales.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.security import require_role
from src.models.product import Product
from src.schemas import sales as schemas

router = APIRouter(prefix="/sales", tags=["Marketing & Promotions"])

@router.post("/campaign/category")
def launch_category_sale(
    campaign: schemas.CategoryCampaign, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Marketing"]))
):
    """Instantly puts an entire category on sale."""
    products = db.query(Product).filter(Product.category == campaign.category_name).all()
    if not products:
        raise HTTPException(status_code=404, detail=f"No products found in category '{campaign.category_name}'.")
        
    for p in products:
        p.discount_percent = campaign.discount_percent
        
    db.commit()
    return {"message": f"SUCCESS: {campaign.discount_percent}% sale applied to {len(products)} items in {campaign.category_name}."}

@router.post("/campaign/brand")
def launch_brand_sale(
    campaign: schemas.BrandCampaign, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Marketing"]))
):
    """Instantly puts a specific brand on sale (e.g., 15% off all Royal Canin)."""
    products = db.query(Product).filter(Product.brand == campaign.brand_name).all()
    if not products:
        raise HTTPException(status_code=404, detail=f"No products found for brand '{campaign.brand_name}'.")
        
    for p in products:
        p.discount_percent = campaign.discount_percent
        
    db.commit()
    return {"message": f"SUCCESS: {campaign.discount_percent}% sale applied to {len(products)} {campaign.brand_name} items."}

@router.post("/campaign/clearance")
def launch_sku_clearance(
    campaign: schemas.ClearanceCampaign, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Marketing"]))
):
    """Applies a specific discount to a custom list of SKUs (Great for expiring batches)."""
    products = db.query(Product).filter(Product.sku.in_(campaign.skus)).all()
    
    if not products:
        raise HTTPException(status_code=404, detail="None of the provided SKUs were found.")
        
    for p in products:
        p.discount_percent = campaign.discount_percent
        
    db.commit()
    return {"message": f"SUCCESS: Clearance discount of {campaign.discount_percent}% applied to {len(products)} specific SKUs."}

@router.post("/end-all")
def end_all_sales(
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin"]))
):
    """THE PANIC BUTTON: Instantly ends all sales and reverts all discounts to 0%."""
    # Only update products that currently have a discount to save database operations
    products_on_sale = db.query(Product).filter(Product.discount_percent > 0).all()
    
    count = len(products_on_sale)
    for p in products_on_sale:
        p.discount_percent = 0.0
        
    db.commit()
    return {"message": f"SALES ENDED: Reverted {count} items back to their base prices."}