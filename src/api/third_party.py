# src/api/third_party.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta

from src.core.database import get_db
from src.core.security import require_role
from src.models.third_party import ClientStorageLog
from src.models.billing import Invoice, InvoiceItem, InvoiceStatus
from src.models.order import Order
from src.models.wms_ops import PickTask, TaskStatus

# --- IMPORT YOUR AUDIT ENGINE ---
from src.services.audit_svc import log_activity

router = APIRouter(prefix="/3pl", tags=["Third-Party Logistics"])

@router.post("/generate-monthly-invoice/{client_id}")
def generate_3pl_monthly_invoice(
    client_id: int, 
    month: int, 
    year: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Finance"]))
):
    """Aggregates 30 days of storage logs and handling fees into one massive monthly client invoice."""
    
    # ==========================================
    # 1. CALCULATE STORAGE FEES
    # ==========================================
    storage_total = db.query(func.sum(ClientStorageLog.daily_fee)).filter(
        ClientStorageLog.client_id == client_id,
        func.extract('month', ClientStorageLog.record_date) == month,
        func.extract('year', ClientStorageLog.record_date) == year
    ).scalar() or 0.0

    # ==========================================
    # 2. CALCULATE HANDLING FEES (The Pick Tasks)
    # ==========================================
    # Find all completed pick tasks for this client's orders this month
    items_handled = db.query(func.sum(PickTask.qty_picked)).join(Order, Order.id == PickTask.order_id).filter(
        Order.customer_id == client_id,
        PickTask.status == TaskStatus.COMPLETED,
        # Assuming your PickTask model has an updated_at or completed_at timestamp
        func.extract('month', PickTask.updated_at) == month, 
        func.extract('year', PickTask.updated_at) == year
    ).scalar() or 0.0

    handling_fee_rate = 1.50  # $1.50 per item picked
    handling_total = round(items_handled * handling_fee_rate, 2)
    
    grand_total = storage_total + handling_total

    if grand_total <= 0:
        raise HTTPException(status_code=400, detail="No storage or handling fees accrued for this client this month.")

    # ==========================================
    # 3. CREATE THE MASTER INVOICE
    # ==========================================
    invoice_number = f"3PL-{year}{month:02d}-{client_id:04d}"
    
    db_invoice = Invoice(
        invoice_number=invoice_number,
        order_id=None, # Service invoice
        due_date=date.today() + timedelta(days=30),
        status=InvoiceStatus.UNPAID,
        subtotal=grand_total,
        tax_total=0.0, 
        grand_total=grand_total,
        amount_paid=0.0
    )
    db.add(db_invoice)
    db.flush()

    # Add Storage Line Item
    if storage_total > 0:
        db.add(InvoiceItem(
            invoice_id=db_invoice.id,
            product_id=None, 
            qty=1,
            unit_price=storage_total,
            line_total=storage_total
        ))
        
    # Add Handling Line Item
    if handling_total > 0:
        db.add(InvoiceItem(
            invoice_id=db_invoice.id,
            product_id=None, 
            qty=items_handled,
            unit_price=handling_fee_rate,
            line_total=handling_total
        ))

    # ==========================================
    # 4. WRITE TO THE IMMUTABLE AUDIT LOG
    # ==========================================
    log_activity(
        db=db,
        username=current_user.username,
        action="3PL_INVOICE_GENERATED",
        entity="Invoice",
        entity_id=db_invoice.id,
        details=f"Generated Monthly 3PL Invoice {invoice_number} for Client ID {client_id}. Storage: ${storage_total} | Handling: ${handling_total} ({items_handled} picks)."
    )

    db.commit()
    db.refresh(db_invoice)
    
    return {
        "message": f"Successfully generated 3PL Invoice {invoice_number}",
        "storage_fees": storage_total,
        "handling_fees": handling_total,
        "grand_total": db_invoice.grand_total,
        "invoice_id": db_invoice.id
    }