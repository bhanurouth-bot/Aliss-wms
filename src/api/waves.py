# src/api/waves.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from src.core.database import get_db
from src.core.security import require_role
from src.models.order import Order, OrderStatus, CustomerType
from src.models.wms_ops import PickingWave, PickTask
from fastapi.responses import StreamingResponse
from src.schemas import wms_ops as wms_schemas
from src.services.pdf_svc import generate_wave_pdf
from src.models.product import Product
from src.models.wms_ops import PickTask, TaskStatus
from src.models.order import Order, OrderStatus, CustomerType
from src.models.wms_ops import PickingWave, PickTask, TaskStatus 
from src.core.database import get_db


router = APIRouter(prefix="/wms/waves", tags=["Smart Wave Picking"])

class WaveGenerateRequest(BaseModel):
    wave_name: str
    order_type: Optional[str] = None      # "B2B" or "B2C"
    is_single_sku: Optional[bool] = None  # True for fast-packing lane
    route: Optional[str] = None           # "EXPRESS"

@router.post("/generate")
def generate_smart_wave(
    payload: WaveGenerateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager"]))
):
    """
    The Batching Engine: Groups matching pending orders and consolidates 
    their items into a single, optimized warehouse walk path.
    """
    # 1. Build the Smart Query
    query = db.query(Order).filter(Order.status == OrderStatus.PENDING)
    
    if payload.order_type:
        query = query.filter(Order.order_type == CustomerType(payload.order_type))
    if payload.is_single_sku is not None:
        query = query.filter(Order.is_single_sku == payload.is_single_sku)
    if payload.route:
        query = query.filter(Order.route == payload.route)
        
    matching_orders = query.all()
    
    if not matching_orders:
        raise HTTPException(status_code=400, detail="No orders match these criteria.")

    # 2. Create the Wave
    wave = PickingWave(wave_name=payload.wave_name)
    db.add(wave)
    db.flush()

    # 3. Consolidate ALL allocations from the matching orders
    aggregated_picks = {} # Dictionary to sum up items in the same bin
    
    for order in matching_orders:
        order.wave_id = wave.id
        # --- UPDATE THIS LINE ---
        order.status = OrderStatus.IN_PROCESS

        # We find the individual pick tasks the FEFO engine already generated for this order
        # and we crush them together!
        existing_tasks = db.query(PickTask).filter(PickTask.order_id == order.id).all()
        
        for task in existing_tasks:
            key = f"{task.product_id}_{task.bin_id}_{task.batch_id}"
            if key in aggregated_picks:
                aggregated_picks[key] += task.qty_expected
            else:
                aggregated_picks[key] = task.qty_expected
                
            # Delete the individual order task, because we are replacing it with a Wave task!
            db.delete(task)

    # 4. Generate the Optimized Wave Tasks
    for key, total_qty in aggregated_picks.items():
        product_id, bin_id, batch_id = key.split("_")
        
        wave_task = PickTask(
            wave_id=wave.id,
            product_id=int(product_id),
            bin_id=int(bin_id),
            batch_id=int(batch_id) if batch_id != "None" else None,
            qty_expected=total_qty
        )
        db.add(wave_task)

    db.commit()
    
    return {
        "message": f"Successfully generated Wave '{wave.wave_name}'",
        "orders_included": len(matching_orders),
        "total_optimized_pick_tasks": len(aggregated_picks)
    }

@router.get("/{wave_id}", response_model=wms_schemas.PickingWaveResponse)
def get_wave_details(
    wave_id: int, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager", "Warehouse Staff"]))
):
    """View the details of a specific Wave and its consolidated pick tasks."""
    wave = db.query(PickingWave).filter(PickingWave.id == wave_id).first()
    if not wave:
        raise HTTPException(status_code=404, detail="Wave not found.")
    return wave


@router.get("/{wave_id}/pdf")
def download_wave_pdf(
    wave_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager", "Warehouse Staff"]))
):
    """Generates a printable PDF for the warehouse worker to take on their walk."""
    pdf_buffer, wave_name = generate_wave_pdf(db, wave_id)
    
    headers = {
        "Content-Disposition": f"attachment; filename=WAVE-{wave_name}.pdf"
    }
    
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers=headers
    )

@router.get("/{wave_id}/orders")
def get_wave_sorting_dashboard(
    wave_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Warehouse Manager", "Warehouse Staff"]))
):
    """
    The Segregation Screen: Gives the packer a clear checklist of every order 
    associated with this wave, and the exact barcodes needed to pack each box.
    """
    wave = db.query(PickingWave).filter(PickingWave.id == wave_id).first()
    if not wave:
        raise HTTPException(status_code=404, detail="Wave not found.")

    dashboard_data = {
        "wave_id": wave.id,
        "wave_name": wave.wave_name,
        "total_orders": len(wave.orders),
        "orders": []
    }

    # Build a clean checklist for the frontend UI
    for order in wave.orders:
        order_data = {
            "order_id": order.id,
            "customer_name": order.customer_name,
            "status": order.status.name,
            "items_to_pack": []
        }
        
        for item in order.items:
            if item.qty_allocated > 0: # Only show items they actually have to pack!
                product = db.query(Product).filter(Product.id == item.product_id).first()
                order_data["items_to_pack"].append({
                    "sku": product.sku,
                    "name": product.name,
                    "expected_barcode": product.barcode, # Show them what to scan!
                    "qty_needed": item.qty_allocated
                })
                
        dashboard_data["orders"].append(order_data)

    return dashboard_data
