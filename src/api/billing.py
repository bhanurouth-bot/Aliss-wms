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

router = APIRouter(prefix="/billing", tags=["Financials & Invoicing"])

@router.post("/generate/{order_id}", response_model=schemas.InvoiceResponse)
def generate_invoice(
    order_id: int, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Finance"]))
):
    """
    Generates a financial invoice based on ACTUAL shipped quantities.
    Applies B2B Wholesale discounts and Net-30 payment terms automatically.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    existing_invoice = db.query(Invoice).filter(Invoice.order_id == order.id).first()
    if existing_invoice:
        raise HTTPException(status_code=400, detail="Invoice already exists for this order.")

    invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{order.id:04d}"
    
    # --- WHOLESALE RULE: B2B buyers get a 20% discount on base price ---
    B2B_DISCOUNT_RATE = 0.20 
    
    db_invoice = Invoice(
        invoice_number=invoice_number,
        order_id=order.id,
        # B2B gets 30 days to pay. B2C is expected to pay immediately.
        due_date=datetime.now() + timedelta(days=30) if order.order_type == CustomerType.B2B else datetime.now(),
        status=InvoiceStatus.UNPAID if order.order_type == CustomerType.B2B else InvoiceStatus.PAID
    )
    db.add(db_invoice)
    db.flush()

    subtotal = 0.0
    tax_total = 0.0
    discount_total = 0.0

    for item in order.items:
        # Crucial ERP Rule: You NEVER bill for backordered items! Only what you allocate/ship.
        if item.qty_allocated <= 0:
            continue 
            
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        # --- THE PRICING SPLIT ---
        if order.order_type == CustomerType.B2B:
            # 1. Start with Base Price, apply 20% discount
            unit_price = product.base_price * (1 - B2B_DISCOUNT_RATE)
            discount_total += (product.base_price - unit_price) * item.qty_allocated
            
            # 2. Add GST explicitly on top of the discounted price
            line_tax = (unit_price * (product.gst_percent / 100)) * item.qty_allocated
            line_total = (unit_price * item.qty_allocated) + line_tax
            
        else:
            # B2C: The customer already agreed to pay the MRP (which includes tax)
            # We just reverse-engineer the tax for the receipt.
            unit_price = product.mrp / (1 + (product.gst_percent / 100))
            line_total = product.mrp * item.qty_allocated
            line_tax = line_total - (unit_price * item.qty_allocated)
            
        subtotal += (unit_price * item.qty_allocated)
        tax_total += line_tax
        
        db_item = InvoiceItem(
            invoice_id=db_invoice.id,
            product_id=product.id,
            qty=item.qty_allocated,
            unit_price=round(unit_price, 2),
            tax_amount=round(line_tax, 2),
            line_total=round(line_total, 2)
        )
        db.add(db_item)

    db_invoice.subtotal = round(subtotal, 2)
    db_invoice.tax_total = round(tax_total, 2)
    db_invoice.discount_total = round(discount_total, 2)
    db_invoice.grand_total = round(subtotal + tax_total, 2)
    
    db.commit()
    db.refresh(db_invoice)
    return db_invoice