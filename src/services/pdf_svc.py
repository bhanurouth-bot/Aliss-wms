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
from src.models.customer import Customer
from src.models.wms_ops import PickTask
from src.models.inventory import ProductBatch
# ==========================================
# MODULAR COMPANY CONFIGURATION
# Edit these details as your business changes
# ==========================================
COMPANY_CONFIG = {
    "name": "Aliss ERP and WMS Services",
    "address": "123 Warehouse Row\nSuite 400\nLogistics City, NY 10001",
    "phone": "+1 (800) 555-0199",
    "email": "billing@petproductserp.com",
    "gst_no": "22AAAAA0000A1Z5", # <--- NEW: Changed to GST No.
    
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

    # --- NEW: Fetch CRM Customer Data ---
    customer = None
    if getattr(order, 'customer_id', None):
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()

    # 1. HEADER (Now uses GST No.)
    doc_title = "TAX INVOICE" if is_b2b else "RETAIL INVOICE"
    header_data = [
        [
            Paragraph(f"<b>{COMPANY_CONFIG['name']}</b><br/>{COMPANY_CONFIG['address'].replace(chr(10), '<br/>')}<br/>GST No.: {COMPANY_CONFIG['gst_no']}<br/>{COMPANY_CONFIG['email']}", normal_style),
            Paragraph(f"<b>{doc_title}</b>", title_style)
        ]
    ]
    elements.append(Table(header_data, colWidths=[400, 330]))
    elements.append(Spacer(1, 15))

    # 2. META DATA (Now includes Customer CRM Info & GST No.)
    contact_phone = getattr(order, 'phone', None) or (customer.phone if customer else "")
    contact_email = getattr(order, 'email', None) or (customer.email if customer else "")
    
    # Format a clean contact string if they exist
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
        # THE NEW APPROACH: DYNAMIC WMS LOOKUP
        # We peek at the warehouse tasks to find the physical batch!
        # ==========================================
        batch_val = "N/A"
        exp_val = "N/A"
        
        # Look for the Pick Tasks associated with this specific order & product
        tasks = db.query(PickTask).filter(
            PickTask.order_id == invoice.order_id,
            PickTask.product_id == item.product_id
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
            
            # If FEFO grabbed from multiple batches, this joins them with a comma!
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
            str(batch_val),             # <--- Dynamically pulled from WMS PickTask
            str(mkt),
            str(exp_val),               # <--- Dynamically pulled from WMS PickTask
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
    
    # --- NEW: Added the Total Tax Row back in! ---
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