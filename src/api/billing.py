# src/api/billing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi.responses import StreamingResponse

from src.core.database import get_db
from src.core.security import require_role
from src.models.order import Order, CustomerType
from src.models.product import Product
from src.models.billing import Invoice, InvoiceItem, InvoiceStatus
from src.schemas import billing as schemas
from src.services.pdf_svc import generate_invoice_pdf

router = APIRouter(prefix="/billing", tags=["Financials & Invoicing"])

@router.post("/generate/{order_id}", response_model=schemas.InvoiceResponse)
def generate_invoice(
    order_id: int, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Finance"]))
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    existing_invoice = db.query(Invoice).filter(Invoice.order_id == order.id).first()
    if existing_invoice:
        raise HTTPException(status_code=400, detail="Invoice already exists for this order.")

    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{order.id:04d}"
    
    B2B_DISCOUNT_PCT = 20.0 
    
    db_invoice = Invoice(
        invoice_number=invoice_number,
        order_id=order.id,
        due_date=datetime.now() + timedelta(days=30) if order.order_type == CustomerType.B2B else datetime.now(),
        status=InvoiceStatus.UNPAID if order.order_type == CustomerType.B2B else InvoiceStatus.PAID
    )
    db.add(db_invoice)
    db.flush()

    subtotal = 0.0
    tax_total = 0.0
    discount_total = 0.0
    target_grand_total = 0.0 

    aggregated_qty = {}
    for item in order.items:
        if item.qty_allocated > 0:
            aggregated_qty[item.product_id] = aggregated_qty.get(item.product_id, 0.0) + item.qty_allocated

    # FRESH, BULLETPROOF MATH LOGIC
    for product_id, qty in aggregated_qty.items():
        product = db.query(Product).filter(Product.id == product_id).first()
        
        # Taxes
        cgst_pct = product.cgst_percent or 0.0
        sgst_pct = product.sgst_percent or 0.0
        total_tax_pct = cgst_pct + sgst_pct
        
        # Prices
        base_rate = product.base_price or 0.0
        mrp = product.mrp or 0.0
        sale_discount_pct = getattr(product, 'discount_percent', 0.0) or 0.0

        if order.order_type == CustomerType.B2B:
            total_discount_pct = B2B_DISCOUNT_PCT + sale_discount_pct
            
            net_rate = base_rate * (1 - (total_discount_pct / 100.0))
            taxable_value = net_rate * qty
            
            cgst_amt = taxable_value * (cgst_pct / 100.0)
            sgst_amt = taxable_value * (sgst_pct / 100.0)
            line_tax = cgst_amt + sgst_amt
            
            line_total = taxable_value + line_tax
            line_discount_amt = (base_rate - net_rate) * qty
            
        else:
            total_discount_pct = sale_discount_pct
            
            discounted_mrp = mrp * (1 - (total_discount_pct / 100.0))
            line_total = discounted_mrp * qty
            
            taxable_value = line_total / (1 + (total_tax_pct / 100.0))
            
            cgst_amt = taxable_value * (cgst_pct / 100.0)
            sgst_amt = taxable_value * (sgst_pct / 100.0)
            line_tax = cgst_amt + sgst_amt
            
            net_rate = taxable_value / qty if qty > 0 else 0.0
            line_discount_amt = (base_rate - net_rate) * qty

        subtotal += taxable_value
        tax_total += line_tax
        discount_total += line_discount_amt
        target_grand_total += line_total
        
        db_item = InvoiceItem(
            invoice_id=db_invoice.id,
            product_id=product.id,
            qty=qty,
            unit_price=round(net_rate, 2),
            discount_amount=round(line_discount_amt, 2), 
            cgst_amount=round(cgst_amt, 2),              
            sgst_amount=round(sgst_amt, 2),              
            tax_amount=round(line_tax, 2),
            line_total=round(line_total, 2)
        )
        db.add(db_item)

    rounded_subtotal = round(subtotal, 2)
    rounded_tax_total = round(tax_total, 2)
    rounded_target_grand = round(target_grand_total, 2) 
    
    calculated_sum = rounded_subtotal + rounded_tax_total
    round_off_value = round(rounded_target_grand - calculated_sum, 2)

    db_invoice.subtotal = rounded_subtotal
    db_invoice.tax_total = rounded_tax_total
    db_invoice.discount_total = round(discount_total, 2)
    db_invoice.round_off = round_off_value
    db_invoice.grand_total = rounded_target_grand
    
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@router.get("/invoice/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Finance"]))
):
    pdf_buffer, invoice_number = generate_invoice_pdf(db, invoice_id)
    headers = {"Content-Disposition": f"attachment; filename={invoice_number}.pdf"}
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)