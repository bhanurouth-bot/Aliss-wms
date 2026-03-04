# src/api/billing.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.schemas import billing as schemas
from src.models.billing import Invoice, InvoiceStatus
from src.core.security import require_role

# Import the logic for calculating totals and creating the database record
from src.services.billing_svc import generate_invoice_from_order

# Import the logic for drawing the physical PDF
from src.services.pdf_svc import generate_invoice_pdf

router = APIRouter(prefix="/billing", tags=["Billing & Invoicing"])

@router.post("/generate/{order_id}", response_model=schemas.InvoiceResponse, status_code=201)
def generate_invoice(order_id: int, db: Session = Depends(get_db)):
    """Generate a financial invoice from an existing Sales Order."""
    return generate_invoice_from_order(db, order_id)

@router.post("/{invoice_id}/pay", response_model=schemas.InvoiceResponse)
def mark_invoice_paid(
    invoice_id: int, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Finance"]))
):
    """Mark an invoice as fully paid (Requires Finance or Admin role)."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    invoice.status = InvoiceStatus.PAID
    db.commit()
    db.refresh(invoice)
    return invoice

@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Finance", "Sales"]))
):
    """Generates and downloads a physical PDF of the invoice."""
    
    # Notice we are calling generate_invoice_pdf here!
    pdf_buffer, inv_number = generate_invoice_pdf(db, invoice_id)
    
    headers = {
        "Content-Disposition": f"attachment; filename={inv_number}.pdf"
    }
    
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers=headers
    )