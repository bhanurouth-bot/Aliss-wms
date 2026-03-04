# src/api/manufacturing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import manufacturing as models
from src.schemas import manufacturing as schemas
from src.services.manufacturing_svc import complete_production_order

router = APIRouter(prefix="/manufacturing", tags=["Manufacturing & BOM"])

@router.post("/boms/", response_model=schemas.BOMResponse, status_code=201)
def create_bom(bom_in: schemas.BOMCreate, db: Session = Depends(get_db)):
    """Define a new recipe (BOM)."""
    db_bom = models.BillOfMaterial(product_id=bom_in.product_id, name=bom_in.name)
    db.add(db_bom)
    db.flush()
    
    for item in bom_in.items:
        db_item = models.BOMItem(
            bom_id=db_bom.id, 
            component_product_id=item.component_product_id, 
            qty_required=item.qty_required
        )
        db.add(db_item)
        
    db.commit()
    db.refresh(db_bom)
    return db_bom

@router.post("/orders/", response_model=schemas.ProductionOrderResponse, status_code=201)
def create_production_order(order_in: schemas.ProductionOrderCreate, db: Session = Depends(get_db)):
    """Schedule a new production run."""
    db_order = models.ProductionOrder(**order_in.model_dump())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@router.post("/orders/{order_id}/complete", response_model=schemas.ProductionOrderResponse)
def complete_production(order_id: int, db: Session = Depends(get_db)):
    """Finish production: consumes raw materials and outputs finished goods."""
    return complete_production_order(db, order_id)