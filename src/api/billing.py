# src/api/billing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from src.core.database import get_db
from src.core.security import require_role
from src.models.order import Order, CustomerType
from src.models.product import Product
from src.models.billing import Invoice, InvoiceItem, InvoiceStatus
from src.schemas import billing as schemas
from fastapi.responses import StreamingResponse
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
    
    B2B_DISCOUNT_RATE = 0.20 
    
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

    # --- THE CRITICAL BUG FIX: ITEM AGGREGATION ---
    # This prevents duplicate phantom rows by merging identical products!
    aggregated_qty = {}
    for item in order.items:
        if item.qty_allocated > 0:
            aggregated_qty[item.product_id] = aggregated_qty.get(item.product_id, 0) + item.qty_allocated

    # Now we loop through the CLEANED, aggregated data to build the bill
    for product_id, qty in aggregated_qty.items():
        product = db.query(Product).filter(Product.id == product_id).first()
        total_tax_percent = product.cgst_percent + product.sgst_percent
        product_sale_discount = getattr(product, 'discount_percent', 0.0) / 100.0
        
        if order.order_type == CustomerType.B2B:
            # B2B gets their flat wholesale rate PLUS the current website sale
            total_discount_rate = B2B_DISCOUNT_RATE + product_sale_discount
            unit_price = product.base_price * (1 - total_discount_rate)
            
            line_discount = (product.base_price - unit_price) * qty
            discount_total += line_discount
            
            cgst = (unit_price * (product.cgst_percent / 100)) * qty
            sgst = (unit_price * (product.sgst_percent / 100)) * qty
            line_tax = cgst + sgst
            
            line_total = (unit_price * qty) + line_tax
            target_grand_total += line_total
            
        else:
            # B2C customers get the dynamic sale discount off the MRP!
            target_line_total = (product.mrp * (1 - product_sale_discount)) * qty
            target_grand_total += target_line_total
            
            # Record how much money the B2C customer saved during the sale
            original_mrp_total = product.mrp * qty
            line_discount = original_mrp_total - target_line_total
            discount_total += line_discount 
            
            # Reverse engineer the taxes from the newly discounted price
            unit_price = target_line_total / (1 + (total_tax_percent / 100)) / qty if qty > 0 else 0
            
            line_tax = target_line_total - (unit_price * qty)
            cgst = line_tax * (product.cgst_percent / total_tax_percent) if total_tax_percent > 0 else 0.0
            sgst = line_tax * (product.sgst_percent / total_tax_percent) if total_tax_percent > 0 else 0.0
            line_total = target_line_total
            
        subtotal += (unit_price * qty)
        tax_total += line_tax
        
        db_item = InvoiceItem(
            invoice_id=db_invoice.id,
            product_id=product.id,
            qty=qty,
            unit_price=round(unit_price, 2),
            discount_amount=round(line_discount, 2), 
            cgst_amount=round(cgst, 2),              
            sgst_amount=round(sgst, 2),              
            tax_amount=round(line_tax, 2),
            line_total=round(line_total, 2)
        )
        db.add(db_item)

    rounded_subtotal = round(subtotal, 2)
    rounded_tax_total = round(tax_total, 2)
    rounded_discount = round(discount_total, 2)
    rounded_target_grand = round(target_grand_total, 2) 
    
    calculated_sum = rounded_subtotal + rounded_tax_total - rounded_discount
    round_off_value = round(rounded_target_grand - calculated_sum, 2)

    db_invoice.subtotal = rounded_subtotal
    db_invoice.tax_total = rounded_tax_total
    db_invoice.discount_total = rounded_discount
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
    """
    Generates and downloads a beautifully formatted PDF copy of the invoice.
    """
    # 1. Generate the PDF in memory
    pdf_buffer, invoice_number = generate_invoice_pdf(db, invoice_id)
    
    # 2. Tell the browser to download it as a file with the correct name
    headers = {
        "Content-Disposition": f"attachment; filename={invoice_number}.pdf"
    }
    
    # 3. Stream the raw bytes back to the user!
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers=headers
    )