# src/services/pdf_svc.py
import io
from fastapi import HTTPException
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape


from src.models.billing import Invoice
from src.models.order import Order, CustomerType
from src.models.product import Product
from src.models.wms_ops import PickingWave
from src.models.wms import Bin


# ==========================================
# MODULAR COMPANY CONFIGURATION
# Edit these details as your business changes
# ==========================================
COMPANY_CONFIG = {
    "name": "Aliss ERP and WMS Services",
    "address": "123 Warehouse Row\nSuite 400\nLogistics City, NY 10001",
    "phone": "+1 (800) 555-0199",
    "email": "billing@petproductserp.com",
    "tax_id": "EIN-99-88776655", # Your Corporate Tax ID/VAT
    
    # B2B Specifics
    "b2b_remittance": "Please remit payment via Wire Transfer.\nBank: Chase Business\nRouting: 111222333 | Acct: 999888777",
    
    # B2C Specifics
    "b2c_return_policy": "Thank you for your purchase! You may return unopened items within 30 days of delivery for a full refund. Please keep this receipt.",
}


def generate_invoice_pdf(db: Session, invoice_id: int):
    """Router: Generates the appropriate PDF invoice based on Customer Type."""
    
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    order = db.query(Order).filter(Order.id == invoice.order_id).first()
    
    if order.order_type == CustomerType.B2B:
        buffer = _generate_b2b_tax_invoice(db, invoice, order)
    else:
        buffer = _generate_b2c_retail_receipt(db, invoice, order)
        
    return buffer, invoice.invoice_number


def _generate_b2b_tax_invoice(db: Session, invoice: Invoice, order: Order) -> io.BytesIO:
    """Generates a strict, 16-column landscape Tax Invoice for B2B Clients."""
    buffer = io.BytesIO()
    
    # FLIP TO LANDSCAPE TO FIT 16 COLUMNS!
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom Styles (BUG FIX: Define center_style here!)
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=2, textColor=colors.darkblue) 
    normal_style = styles['Normal']
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], alignment=1)
    tiny_style = ParagraphStyle('Tiny', parent=styles['Normal'], fontSize=7, leading=8)

    # 1. HEADER 
    header_data = [
        [
            Paragraph(f"<b>{COMPANY_CONFIG['name']}</b><br/>{COMPANY_CONFIG['address'].replace(chr(10), '<br/>')}<br/>Tax ID: {COMPANY_CONFIG['tax_id']}<br/>{COMPANY_CONFIG['email']}", normal_style),
            Paragraph("<b>TAX INVOICE</b>", title_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[400, 330])
    elements.append(header_table)
    elements.append(Spacer(1, 15))

    # 2. META DATA & BUYER INFO
    buyer_info = f"<b>BILL TO:</b><br/>{order.company_name or order.customer_name}<br/>"
    if order.tax_id: buyer_info += f"Tax ID: {order.tax_id}<br/>"
    if order.billing_address: buyer_info += f"{order.billing_address.replace(chr(10), '<br/>')}"
    
    meta_info = f"<b>Invoice Number:</b> {invoice.invoice_number}<br/>" \
                f"<b>Date:</b> {invoice.created_at.strftime('%Y-%m-%d')}<br/>" \
                f"<b>PO Number:</b> {order.po_number or 'N/A'}<br/>" \
                f"<b>Terms:</b> {order.payment_terms or 'Net 30'}"

    meta_table = Table([[Paragraph(buyer_info, normal_style), Paragraph(meta_info, normal_style)]], colWidths=[400, 330])
    elements.append(meta_table)
    elements.append(Spacer(1, 15))

    # 3. THE MASSIVE 16-COLUMN GRID
    # Column Headers
    table_data = [[
        "SR", "Desc/Name", "HSN", "Qty", "Unit", "Batch", "Mkt", "Exp Dt", 
        "MRP", "Rate", "Disc", "Net Rate", "Taxable", "CGST", "SGST", "Amount"
    ]]
    
    for idx, item in enumerate(invoice.items, start=1):
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        # We use getattr() with fallbacks because these fields might not exist in your DB yet!
        hsn = getattr(product, 'hsn_code', 'N/A')
        unit = getattr(product, 'uom', 'PCS')
        mkt = getattr(product, 'brand', 'N/A')
        mrp = getattr(product, 'mrp', 0.0)
        base_rate = getattr(product, 'base_price', item.unit_price)
        
        # Batch and Expiry are typically joined from the Inventory/Batch table during picking.
        # We will hardcode 'N/A' until we update the InvoiceItem database table to store them.
        batch = "N/A"
        exp_dt = "N/A"
        
        # Calculations
        disc_amount = base_rate - item.unit_price if base_rate > item.unit_price else 0.0
        taxable_val = item.unit_price * item.qty
        
        # Split total GST 50/50 for CGST and SGST
        cgst = item.tax_amount / 2
        sgst = item.tax_amount / 2
        
        table_data.append([
            str(idx),
            Paragraph(product.name if product else "Product", tiny_style),
            hsn,
            str(item.qty),
            unit,
            batch,
            mkt,
            exp_dt,
            f"{mrp:.2f}",
            f"{base_rate:.2f}",
            f"{disc_amount:.2f}",
            f"{item.unit_price:.2f}",
            f"{taxable_val:.2f}",
            f"{cgst:.2f}",
            f"{sgst:.2f}",
            f"{item.line_total:.2f}"
        ])

    # 4. FOOTER TOTALS (Spanning across the columns)
    # We append empty strings to push the totals to the far right columns
    table_data.append([
        "", "", "", "", "", "", "", "", "", "", "", "", 
        "SUBTOTAL:", "", "", f"${invoice.subtotal:.2f}"
    ])
    if getattr(invoice, 'round_off', 0.0) != 0.0:
        sign = "+" if invoice.round_off > 0 else ""
        table_data.append([
            "", "", "", "", "", "", "", "", "", "", "", "", 
            "ROUND OFF:", "", "", f"{sign}${invoice.round_off:.2f}"
        ])
    table_data.append([
        "", "", "", "", "", "", "", "", "", "", "", "", 
        "GRAND TOTAL:", "", "", f"${invoice.grand_total:.2f}"
    ])

    # 16 Column Widths perfectly balanced for Landscape Letter (Total ~750 points)
    col_widths = [20, 110, 40, 30, 30, 40, 40, 45, 40, 40, 40, 45, 50, 40, 40, 50]
    
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), # Center all by default
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Left align Product Name
        ('ALIGN', (8, 1), (-1, -1), 'RIGHT'),  # Right align all currency values
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),     # TINY font to fit 16 columns!
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -4), 0.5, colors.lightgrey), # Grid for items
        # Styling for the Totals at the bottom
        ('SPAN', (12, -3), (14, -3)), # Span "SUBTOTAL:" across 3 columns
        ('SPAN', (12, -2), (14, -2)), 
        ('SPAN', (12, -1), (14, -1)), 
        ('FONTNAME', (12, -3), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (12, -3), (-1, -1), 1, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # 5. REMITTANCE INSTRUCTIONS
    elements.append(Paragraph("<b>Payment Instructions:</b>", normal_style))
    elements.append(Paragraph(COMPANY_CONFIG['b2b_remittance'].replace(chr(10), '<br/>'), normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def _generate_b2c_retail_receipt(db: Session, invoice: Invoice, order: Order) -> io.BytesIO:
    """Generates a comprehensive 16-column landscape Retail Invoice for B2C Consumers."""
    buffer = io.BytesIO()
    
    # Use landscape mode to fit 16 columns!
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=2, textColor=colors.darkblue) 
    normal_style = styles['Normal']
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], alignment=1)
    tiny_style = ParagraphStyle('Tiny', parent=styles['Normal'], fontSize=7, leading=8)

    # 1. HEADER 
    header_data = [
        [
            Paragraph(f"<b>{COMPANY_CONFIG['name']}</b><br/>{COMPANY_CONFIG['address'].replace(chr(10), '<br/>')}<br/>{COMPANY_CONFIG['email']} | {COMPANY_CONFIG['phone']}", normal_style),
            Paragraph("<b>RETAIL INVOICE</b>", title_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[400, 330])
    elements.append(header_table)
    elements.append(Spacer(1, 15))

    # 2. META DATA & BUYER INFO
    buyer_info = f"<b>CUSTOMER:</b><br/>{order.customer_name}<br/>"
    if order.shipping_address: buyer_info += f"<b>Ship To:</b><br/>{order.shipping_address.replace(chr(10), '<br/>')}"
    
    meta_info = f"<b>Receipt Number:</b> {invoice.invoice_number}<br/>" \
                f"<b>Date:</b> {invoice.created_at.strftime('%Y-%m-%d')}<br/>"
                
    meta_table = Table([[Paragraph(buyer_info, normal_style), Paragraph(meta_info, normal_style)]], colWidths=[400, 330])
    elements.append(meta_table)
    elements.append(Spacer(1, 15))

    # 3. 16-COLUMN GRID
    table_data = [[
        "SR", "Desc/Name", "HSN", "Qty", "Unit", "Batch", "Mkt", "Exp Dt", 
        "MRP", "Rate", "Disc", "Net Rate", "Taxable", "CGST", "SGST", "Amount"
    ]]
    
    for idx, item in enumerate(invoice.items, start=1):
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        hsn = getattr(product, 'hsn_code', 'N/A')
        unit = getattr(product, 'uom', 'PCS')
        mkt = getattr(product, 'brand', 'N/A')
        mrp = getattr(product, 'mrp', item.line_total/item.qty if item.qty>0 else 0.0)
        
        # B2C Math differences: the item.unit_price in DB is the tax-exclusive back-calculated price.
        base_rate = item.unit_price
        disc_amount = 0.0 # B2C doesn't have the wholesale discount applied here
        taxable_val = item.unit_price * item.qty
        
        cgst = item.tax_amount / 2
        sgst = item.tax_amount / 2
        
        table_data.append([
            str(idx),
            Paragraph(product.name if product else "Product", tiny_style),
            hsn,
            str(item.qty),
            unit,
            "N/A", # Batch
            mkt,
            "N/A", # Exp
            f"{mrp:.2f}",
            f"{base_rate:.2f}",
            f"{disc_amount:.2f}",
            f"{item.unit_price:.2f}",
            f"{taxable_val:.2f}",
            f"{cgst:.2f}",
            f"{sgst:.2f}",
            f"{item.line_total:.2f}"
        ])

    # 4. FOOTER TOTALS 
    table_data.append([
        "", "", "", "", "", "", "", "", "", "", "", "", 
        "SUBTOTAL:", "", "", f"${invoice.subtotal:.2f}"
    ])
    if getattr(invoice, 'round_off', 0.0) != 0.0:
        sign = "+" if invoice.round_off > 0 else ""
        table_data.append([
            "", "", "", "", "", "", "", "", "", "", "", "", 
            "ROUND OFF:", "", "", f"{sign}${invoice.round_off:.2f}"
        ])
    table_data.append([
        "", "", "", "", "", "", "", "", "", "", "", "", 
        "GRAND TOTAL:", "", "", f"${invoice.grand_total:.2f}"
    ])

    col_widths = [20, 110, 40, 30, 30, 40, 40, 45, 40, 40, 40, 45, 50, 40, 40, 50]
    
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),    
        ('ALIGN', (8, 1), (-1, -1), 'RIGHT'),  
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),     
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -4), 0.5, colors.lightgrey), 
        ('SPAN', (12, -3), (14, -3)), 
        ('SPAN', (12, -2), (14, -2)), 
        ('SPAN', (12, -1), (14, -1)), 
        ('FONTNAME', (12, -3), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (12, -3), (-1, -1), 1, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))

    # 5. RETURN POLICY
    elements.append(Paragraph(COMPANY_CONFIG['b2c_return_policy'], center_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_wave_pdf(db: Session, wave_id: int):
    """Generates a professional Bulk Wave Picklist PDF."""
    
    wave = db.query(PickingWave).filter(PickingWave.id == wave_id).first()
    if not wave:
        raise HTTPException(status_code=404, detail="Wave not found")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Header
    elements.append(Paragraph("PET PRODUCTS ENTERPRISE", styles['Heading1']))
    elements.append(Paragraph(f"BULK WAVE PICKLIST: {wave.wave_name}", styles['Heading2']))
    elements.append(Paragraph(f"Status: {wave.status.name}", styles['Normal']))
    elements.append(Paragraph(f"Total Orders Grouped: {len(wave.orders)}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Table Data
    table_data = [["Bin Location", "SKU / Product", "Expected Qty", "Check (✓)"]]
    
    # We want to sort tasks by Bin Location to make the worker's walk efficient!
    tasks_with_locations = []
    for task in wave.tasks:
        product = db.query(Product).filter(Product.id == task.product_id).first()
        bin_record = db.query(Bin).filter(Bin.id == task.bin_id).first()
        
        tasks_with_locations.append({
            "bin": bin_record.location_code if bin_record else "Unknown",
            "sku": product.sku if product else "Unknown",
            "name": product.name if product else "Unknown",
            "qty": task.qty_expected
        })
        
    # Sort alphabetically by Bin Location
    tasks_with_locations.sort(key=lambda x: x["bin"])

    for item in tasks_with_locations:
        table_data.append([
            item["bin"],
            f"{item['sku']}\n{item['name']}",
            str(item["qty"]),
            "" # Empty box for the worker to check off with a pen
        ])

    # Table Styling
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkorange),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])
    
    t = Table(table_data, colWidths=[100, 200, 100, 80])
    t.setStyle(table_style)
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    
    return buffer, wave.wave_name

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