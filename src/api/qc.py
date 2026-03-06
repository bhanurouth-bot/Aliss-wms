# src/api/qc.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.core.database import get_db
from src.core.security import require_role
from src.models.order import Order, OrderStatus
# Assume you have a PDF service to generate bills
# from src.services.pdf_svc import generate_invoice_pdf 

router = APIRouter(prefix="/wms/qc", tags=["Quality Control & Billing"])

class VerifyOrderRequest(BaseModel):
    # Could include a list of scanned item barcodes if you want strict QC validation
    pass 

@router.post("/orders/{order_id}/verify-and-bill")
def verify_order_and_print_bill(
    order_id: int, 
    # payload: VerifyOrderRequest, # Uncomment if you want strict item verification at QC
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "QC Staff", "Warehouse Manager"]))
):
    """
    Confirms the physical items have arrived at the QC desk, generates the bill, 
    and moves the order to the Packing lane.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    # Enforce strict linear workflow: Order MUST be picked and waiting for checks
    if order.status != OrderStatus.CHECKING:
        raise HTTPException(
            status_code=400, 
            detail=f"Order must be in CHECKING state. Currently: {order.status.name}"
        )

    # --- [Optional: Logic to strictly verify scanned barcodes against order items] ---
    
    # --- [Logic to generate the PDF Bill] ---
    # pdf_buffer, invoice_number = generate_invoice_pdf(db, order.id)
    invoice_number = f"INV-{order.id}000" # Placeholder
    
    # Move the order state to the PACKING lane
    order.status = OrderStatus.PACKING
    db.commit()
    db.refresh(order)
    
    return {
        "message": "Order successfully verified and bill generated.",
        "order_id": order.id,
        "invoice_number": invoice_number,
        "previous_status": "CHECKING",
        "current_status": order.status.name,
        "bill_download_url": f"/api/billing/download/{order.id}" # Link frontend can use to auto-print
    }