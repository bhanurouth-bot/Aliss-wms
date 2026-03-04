# src/api/wms_ops.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import wms_ops as models
from src.models import wms as wms_models
from src.schemas import wms_ops as schemas
from src.services.wms_svc import confirm_pick_task
from fastapi.responses import StreamingResponse
from src.services.pdf_svc import generate_picklist_pdf

router = APIRouter(prefix="/wms/ops", tags=["WMS Operations"])

@router.get("/picklists/{order_id}", response_model=schemas.PicklistResponse)
def get_picklist_for_order(order_id: int, db: Session = Depends(get_db)):
    """Fetch the optimized picklist for a specific order."""
    
    picklist = db.query(models.Picklist).filter(models.Picklist.order_id == order_id).first()
    if not picklist:
        raise HTTPException(status_code=404, detail="Picklist not found for this order.")
        
    # Sort the tasks by physical Bin location code for the warehouse worker
    sorted_tasks = (
        db.query(models.PickTask)
        .join(wms_models.Bin, models.PickTask.bin_id == wms_models.Bin.id)
        .filter(models.PickTask.picklist_id == picklist.id)
        .order_by(wms_models.Bin.location_code.asc())
        .all()
    )
    
    # Attach the sorted tasks to the picklist response
    picklist.tasks = sorted_tasks
    return picklist

@router.post("/pick-tasks/{task_id}/confirm", response_model=schemas.PickTaskResponse)
def scanner_confirm_pick(
    task_id: int, 
    payload: schemas.PickConfirmation, 
    db: Session = Depends(get_db)
):
    """
    Endpoint used by handheld warehouse scanners. 
    Verifies barcodes and deducts reserved stock.
    """
    return confirm_pick_task(
        db=db, 
        task_id=task_id, 
        scanned_bin=payload.scanned_bin_barcode, 
        scanned_product=payload.scanned_product_barcode, 
        qty_picked=payload.qty_picked
    )

@router.get("/picklist/{picklist_id}/pdf")
async def get_picklist_pdf(picklist_id: str):
    # 1. Fetch picklist data from DB (mocked here for example)
    # picklist = db.query(Picklist).filter(id=picklist_id).first()
    
    # 2. Generate PDF
    pdf_buffer = generate_picklist_pdf(picklist_data)
    
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=picklist_{picklist_id}.pdf"}
    )