# src/services/pdf_svc.py
import io
from fastapi import HTTPException
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from src.models.billing import Invoice
from src.models.order import Order
from src.models.product import Product

def generate_picklist_pdf(picklist_data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph(f"Picklist: {picklist_data['picklist_id']}", styles['Title']))
    elements.append(Spacer(1, 12))

    # Table Header
    data = [["SKU", "Product Name", "Location", "Quantity"]]
    
    # Add Items
    for item in picklist_data['items']:
        data.append([
            item['sku'], 
            item['name'], 
            item.get('bin_location', 'N/A'), 
            str(item['quantity'])
        ])

    # Styling the Table
    t = Table(data, colWidths=[80, 250, 80, 60])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.indigo),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

    
def generate_invoice_pdf(db: Session, invoice_id: int):
    """Generates a professional PDF invoice in memory."""
    
    # 1. Fetch the data
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    order = db.query(Order).filter(Order.id == invoice.order_id).first()

    # 2. Setup the PDF Buffer and Document
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # 3. Build the Header
    elements.append(Paragraph("PET PRODUCTS ENTERPRISE", styles['Heading1']))
    elements.append(Paragraph(f"INVOICE: {invoice.invoice_number}", styles['Heading2']))
    elements.append(Paragraph(f"Customer: {order.customer_name}", styles['Normal']))
    elements.append(Paragraph(f"Date Generated: {invoice.created_at.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"Status: {invoice.status.name}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # 4. Build the Table Data
    table_data = [["Product Name", "Qty", "Base Price", "Tax (GST)", "Line Total"]]
    
    for item in invoice.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        product_name = product.name if product else "Unknown SKU"
        
        table_data.append([
            product_name,
            str(item.qty),
            f"${item.unit_base_price:.2f}",
            f"${item.tax_amount:.2f}",
            f"${item.line_total:.2f}"
        ])

    # 5. Add Totals to the bottom of the table
    table_data.append(["", "", "", "SUBTOTAL:", f"${invoice.subtotal:.2f}"])
    table_data.append(["", "", "", "TAX TOTAL:", f"${invoice.tax_total:.2f}"])
    table_data.append(["", "", "", "GRAND TOTAL:", f"${invoice.grand_total:.2f}"])

    # 6. Apply Professional Styling to the Table
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        # Highlight the Grand Total row
        ('BACKGROUND', (3, -1), (-1, -1), colors.lightgreen),
        ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
    ])
    
    t = Table(table_data)
    t.setStyle(table_style)
    elements.append(t)

    # 7. Compile the PDF
    doc.build(elements)
    
    # 8. Rewind the buffer to the beginning so FastAPI can read it
    buffer.seek(0)
    
    return buffer, invoice.invoice_number