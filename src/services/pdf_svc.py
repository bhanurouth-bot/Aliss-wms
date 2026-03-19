# src/services/pdf_svc.py
import io
from fastapi import HTTPException
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- NEW: ReportLab Barcode & Unit Imports for Shipping Labels ---
from reportlab.lib.units import inch
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import Drawing

from src.models.billing import Invoice
from src.models.order import Order, CustomerType
from src.models.product import Product
from src.models.wms_ops import PickingWave, WarehouseTask
from src.models.wms import Bin
from src.models.inventory import ProductBatch
from src.models.customer import Customer
from src.models.shipping import ShippingManifest

# ==========================================
# MODULAR COMPANY CONFIGURATION
# ==========================================
COMPANY_CONFIG = {
    "name": "Aliss ERP and WMS Services",
    "address": "123 Warehouse Row\nSuite 400\nLogistics City, NY 10001",
    "phone": "+1 (800) 555-0199",
    "email": "billing@petproductserp.com",
    "gst_no": "22AAAAA0000A1Z5", # <--- Updated to GST No.
    
    # B2B Specifics
    "b2b_remittance": "Please remit payment via Wire Transfer.\nBank: Chase Business\nRouting: 111222333 | Acct: 999888777",
    
    # B2C Specifics
    "b2c_return_policy": "Thank you for your purchase! You may return unopened items within 30 days of delivery for a full refund. Please keep this receipt.",
}


def generate_invoice_pdf(db: Session, invoice_id: int):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    order = db.query(Order).filter(Order.id == invoice.order_id).first()
    
    # We now use the SAME unbreakable grid for both types
    buffer = _generate_tax_invoice(db, invoice, order, is_b2b=(order.order_type == CustomerType.B2B))
        
    return buffer, invoice.invoice_number


def _generate_tax_invoice(db: Session, invoice: Invoice, order: Order, is_b2b: bool) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=2, textColor=colors.darkblue) 
    normal_style = styles['Normal']
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], alignment=1)
    tiny_style = ParagraphStyle('Tiny', parent=styles['Normal'], fontSize=7, leading=8)

    # --- Fetch CRM Customer Data ---
    customer = None
    if getattr(order, 'customer_id', None):
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()

    # 1. HEADER (Using GST No.)
    doc_title = "TAX INVOICE" if is_b2b else "RETAIL INVOICE"
    header_data = [
        [
            Paragraph(f"<b>{COMPANY_CONFIG['name']}</b><br/>{COMPANY_CONFIG['address'].replace(chr(10), '<br/>')}<br/>GST No.: {COMPANY_CONFIG['gst_no']}<br/>{COMPANY_CONFIG['email']}", normal_style),
            Paragraph(f"<b>{doc_title}</b>", title_style)
        ]
    ]
    elements.append(Table(header_data, colWidths=[400, 330]))
    elements.append(Spacer(1, 15))

    # 2. META DATA (Includes CRM Info)
    contact_phone = getattr(order, 'phone', None) or (customer.phone if customer else "")
    contact_email = getattr(order, 'email', None) or (customer.email if customer else "")
    
    contact_str = ""
    if contact_phone or contact_email:
        contact_parts = [p for p in [contact_phone, contact_email] if p]
        contact_str = f"<br/>{' | '.join(contact_parts)}"

    if is_b2b:
        buyer_info = f"<b>BILL TO:</b><br/>{order.company_name or order.customer_name}{contact_str}<br/>GST No.: {order.tax_id or 'N/A'}<br/>{str(order.billing_address or 'No Address Provided').replace(chr(10), '<br/>')}"
    else:
        buyer_info = f"<b>CUSTOMER:</b><br/>{order.customer_name}{contact_str}<br/><br/><b>Ship To:</b><br/>{str(order.shipping_address or 'None').replace(chr(10), '<br/>')}"
    
    meta_info = f"<b>Invoice Number:</b> {invoice.invoice_number}<br/><b>Date:</b> {invoice.created_at.strftime('%Y-%m-%d')}<br/>"
    if is_b2b:
        meta_info += f"<b>PO Number:</b> {order.po_number or 'N/A'}<br/><b>Terms:</b> {order.payment_terms or 'Net 30'}"

    elements.append(Table([[Paragraph(buyer_info, normal_style), Paragraph(meta_info, normal_style)]], colWidths=[400, 330]))
    elements.append(Spacer(1, 15))

    # 3. STRICT 16-COLUMN GRID
    table_data = [[
        "SR", "Desc/Name", "HSN", "Qty", "Unit", "Batch", "Mkt", "Exp Dt", 
        "MRP", "Rate", "Disc %", "Net Rate", "Taxable", "CGST", "SGST", "Amount"
    ]]
    
    for idx, item in enumerate(invoice.items, start=1):
        product = db.query(Product).filter(Product.id == item.product_id).first()
        
        hsn = getattr(product, 'hsn_code', 'N/A') or 'N/A'
        unit = getattr(product, 'uom', 'PCS') or 'PCS'
        mkt = getattr(product, 'brand', 'N/A') or 'N/A'
        
        mrp = getattr(product, 'mrp', 0.0) or 0.0
        base_rate = getattr(product, 'base_price', 0.0) or 0.0
        
        disc_pct = getattr(product, 'discount_percent', 0.0) or 0.0
        if is_b2b:
            disc_pct += 20.0 
            
        taxable_val = item.unit_price * item.qty
        
        # ==========================================
        # DYNAMIC WMS LOOKUP (WAVE-AWARE)
        # ==========================================
        batch_val = "N/A"
        exp_val = "N/A"
        
        # Check if this order was crushed into a Wave!
        if getattr(order, 'wave_id', None):
            tasks = db.query(WarehouseTask).filter(
                WarehouseTask.wave_id == order.wave_id,
                WarehouseTask.product_id == item.product_id
            ).all()
        else:
            # It was a single order picked by itself
            tasks = db.query(WarehouseTask).filter(
                WarehouseTask.order_id == invoice.order_id,
                WarehouseTask.product_id == item.product_id
            ).all()
        
        if tasks:
            batches = []
            exps = []
            for task in tasks:
                if task.batch_id:
                    batch = db.query(ProductBatch).filter(ProductBatch.id == task.batch_id).first()
                    if batch:
                        if batch.batch_number and batch.batch_number not in batches:
                            batches.append(batch.batch_number)
                        if batch.expiry_date:
                            exp_str = batch.expiry_date.strftime('%Y-%m-%d')
                            if exp_str not in exps:
                                exps.append(exp_str)
            
            if batches:
                batch_val = ", ".join(batches)
            if exps:
                exp_val = ", ".join(exps)
        # ==========================================
        
        table_data.append([
            str(idx),
            Paragraph(product.name if product else "Product", tiny_style),
            str(hsn),
            str(item.qty),
            str(unit),
            str(batch_val),             
            str(mkt),
            str(exp_val),               
            f"{mrp:.2f}",               
            f"{base_rate:.2f}",                 
            f"{disc_pct:.2f}%",         
            f"{item.unit_price:.2f}",   
            f"{taxable_val:.2f}",       
            f"{item.cgst_amount:.2f}",  
            f"{item.sgst_amount:.2f}",  
            f"{item.line_total:.2f}"    
        ])

    # 4. FOOTER TOTALS
    footer_start_row = len(table_data)
    
    table_data.append(["", "", "", "", "", "", "", "", "", "", "", "", "SUBTOTAL:", "", "", f"${invoice.subtotal:.2f}"])
    table_data.append(["", "", "", "", "", "", "", "", "", "", "", "", "TOTAL TAX:", "", "", f"${invoice.tax_total:.2f}"])
    
    if getattr(invoice, 'round_off', 0.0) != 0.0:
        sign = "+" if invoice.round_off > 0 else ""
        table_data.append(["", "", "", "", "", "", "", "", "", "", "", "", "ROUND OFF:", "", "", f"{sign}${invoice.round_off:.2f}"])
        
    table_data.append(["", "", "", "", "", "", "", "", "", "", "", "", "GRAND TOTAL:", "", "", f"${invoice.grand_total:.2f}"])

    footer_end_row = len(table_data) - 1

    col_widths = [20, 110, 40, 30, 30, 40, 40, 45, 40, 40, 40, 45, 50, 40, 40, 50]
    t = Table(table_data, colWidths=col_widths)
    
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), 
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),    
        ('ALIGN', (8, 1), (-1, -1), 'RIGHT'),  
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),     
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, footer_start_row - 1), 0.5, colors.lightgrey), 
        ('FONTNAME', (12, footer_start_row), (-1, footer_end_row), 'Helvetica-Bold'),
        ('LINEABOVE', (12, footer_start_row), (-1, footer_end_row), 1, colors.black),
    ]

    for row_idx in range(footer_start_row, footer_end_row + 1):
        base_style.append(('SPAN', (12, row_idx), (14, row_idx)))

    t.setStyle(TableStyle(base_style))
    elements.append(t)
    elements.append(Spacer(1, 20))

    if is_b2b:
        elements.append(Paragraph("<b>Payment Instructions:</b>", normal_style))
        elements.append(Paragraph(COMPANY_CONFIG['b2b_remittance'].replace(chr(10), '<br/>'), normal_style))
    else:
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
        
    tasks_with_locations.sort(key=lambda x: x["bin"])

    for item in tasks_with_locations:
        table_data.append([
            item["bin"],
            f"{item['sku']}\n{item['name']}",
            str(item["qty"]),
            "" 
        ])

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

    elements.append(Paragraph(f"Picklist: {picklist_data['picklist_id']}", styles['Title']))
    elements.append(Spacer(1, 12))

    data = [["SKU", "Product Name", "Location", "Quantity"]]
    
    for item in picklist_data['items']:
        data.append([
            item['sku'], 
            item['name'], 
            item.get('bin_location', 'N/A'), 
            str(item['quantity'])
        ])

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


def generate_shipping_label_pdf(db: Session, order_id: int, requested_carrier: str = "FEDEX") -> tuple[io.BytesIO, str]:
    """Generates a 4x6 inch thermal shipping label with a tracking barcode and Route ID."""
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # --- THE CHICKEN AND EGG RESOLVER ---
    manifest = db.query(ShippingManifest).filter(ShippingManifest.order_id == order.id).first()
    
    if manifest:
        tracking_number = manifest.tracking_number
        carrier = manifest.carrier.upper()
    else:
        # Dynamically set the carrier and mock tracking prefix!
        carrier = requested_carrier.upper()
        # Grab the first 3 letters for the mock tracking prefix (e.g., UPS, DHL, USP)
        prefix = carrier[:3].upper() if len(carrier) >= 3 else "TRK"
        tracking_number = f"{prefix}-{order.id:010d}"
    # ---------------------------------------------

    buffer = io.BytesIO()
    
    # Standard Thermal Label Size: 4x6 inches
    PAGE_SIZE = (4 * inch, 6 * inch)
    doc = SimpleDocTemplate(buffer, pagesize=PAGE_SIZE, rightMargin=15, leftMargin=15, topMargin=15, bottomMargin=15)
    
    elements = []
    styles = getSampleStyleSheet()
    
    sender_style = ParagraphStyle('Sender', parent=styles['Normal'], fontSize=8, leading=10)
    recipient_style = ParagraphStyle('Recipient', parent=styles['Normal'], fontSize=12, leading=14, leftIndent=20)
    
    # ==========================================
    # 1. CARRIER & ORDER TYPE HEADER (30% Split)
    # ==========================================
    carrier_style = ParagraphStyle(
        'CarrierStyle', parent=styles['Heading1'], alignment=0, fontSize=16, leading=20
    )
    type_style = ParagraphStyle(
        'TypeStyle', parent=styles['Heading1'], alignment=0, fontSize=24, leading=28
    )
    
    # Extract B2B/B2C safely
    order_type_str = order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type)
    
    # Append Route if it exists
    if getattr(order, 'route', None):
        display_text = f"{order_type_str} - {order.route.upper()}"
    else:
        display_text = order_type_str
    
    # Create the 2-column header layout
    header_table = Table([
        [Paragraph(f"<b>{carrier}</b>", carrier_style), Paragraph(f"<b>{display_text}</b>", type_style)]
    ], colWidths=[85, 173])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    
    elements.append(header_table)
    elements.append(Spacer(1, 15))
    
    # ==========================================
    # 2. RETURN ADDRESS 
    # ==========================================
    sender_text = f"<b>FROM:</b><br/>{COMPANY_CONFIG['name']}<br/>{COMPANY_CONFIG['address'].replace(chr(10), '<br/>')}<br/>{COMPANY_CONFIG['phone']}"
    elements.append(Paragraph(sender_text, sender_style))
    elements.append(Spacer(1, 20))
    
    # ==========================================
    # 3. SHIP TO ADDRESS
    # ==========================================
    contact_str = f"<br/>{order.phone}" if order.phone else ""
    ship_to_text = f"<b>SHIP TO:</b><br/>{order.customer_name}{contact_str}<br/>{str(order.shipping_address or 'No Address Provided').replace(chr(10), '<br/>')}"
    elements.append(Paragraph(ship_to_text, recipient_style))
    elements.append(Spacer(1, 30))
    
    # ==========================================
    # 4. TRACKING BARCODE
    # ==========================================
    barcode = createBarcodeDrawing('Code128', value=tracking_number, barHeight=0.8*inch, barWidth=1.2)
    barcode.hAlign = 'CENTER' 
    
    elements.append(barcode)
    elements.append(Spacer(1, 5))
    
    # ==========================================
    # 5. TRACKING NUMBER TEXT
    # ==========================================
    tracking_text = ParagraphStyle('TrackTxt', parent=styles['Normal'], alignment=1, fontSize=10)
    elements.append(Paragraph(f"<b>TRK# {tracking_number}</b>", tracking_text))
    
    # Order Reference at the very bottom
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Ref Order: {order.id}", sender_style))

    doc.build(elements)
    buffer.seek(0)
    
    return buffer, tracking_number