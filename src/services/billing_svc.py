# src/services/billing_svc.py (Complete replacement)
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from src.models.billing import Invoice, InvoiceItem, InvoiceStatus
from src.models.order import Order
from src.models.product import Product

def generate_invoice_from_order(db: Session, order_id: int):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
        
    existing = db.query(Invoice).filter(Invoice.order_id == order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Invoice already exists.")

    inv_number = f"INV-{datetime.now().strftime('%Y%m')}-{order.id:04d}"
    invoice = Invoice(order_id=order.id, invoice_number=inv_number)
    db.add(invoice)
    db.flush()

    subtotal = 0.0
    tax_total = 0.0
    grand_total = 0.0

    for item in order.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        # Pull values from the product master
        qty = item.qty_ordered
        mrp = product.mrp if product else 0.0
        base_price = product.base_price if product else 0.0
        
        # Calculate line financials
        line_base_total = qty * base_price
        line_grand_total = qty * mrp
        line_tax = line_grand_total - line_base_total # The difference is the tax amount
        
        # Add to invoice running totals
        subtotal += line_base_total
        tax_total += line_tax
        grand_total += line_grand_total
        
        inv_item = InvoiceItem(
            invoice_id=invoice.id,
            product_id=item.product_id,
            qty=qty,
            unit_base_price=round(base_price, 2),
            tax_amount=round(line_tax, 2),
            line_total=round(line_grand_total, 2)
        )
        db.add(inv_item)

    # Set final invoice header totals
    invoice.subtotal = round(subtotal, 2)
    invoice.tax_total = round(tax_total, 2)
    invoice.grand_total = round(grand_total, 2)

    db.commit()
    db.refresh(invoice)
    return invoice