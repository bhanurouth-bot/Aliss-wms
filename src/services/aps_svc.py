# src/services/aps_svc.py
import math
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.models.aps import ProductMetrics
from src.models.inventory import Inventory
# --- 1. Import the CORRECT models from the new Procurement Module ---
from src.models.purchase import PurchaseOrder, PurchaseOrderItem, Supplier, POStatus

def run_replenishment_engine(db: Session):
    """Calculates Reorder Points and auto-generates Draft POs."""
    
    metrics = db.query(ProductMetrics).all()
    recommendations = []
    
    # --- 2. Ensure we have a default Supplier in the database for Auto-Drafts ---
    default_supplier = db.query(Supplier).filter(Supplier.name == "Auto-Generated Default Supplier").first()
    if not default_supplier:
        default_supplier = Supplier(
            name="Auto-Generated Default Supplier", 
            contact_email="auto_procurement@erp.com", 
            phone="0000000000"
        )
        db.add(default_supplier)
        db.flush()

    for metric in metrics:
        # 1. Apply the Formulas
        safety_stock = metric.service_level_z_score * metric.demand_std_dev * math.sqrt(metric.lead_time_days)
        reorder_point = (metric.avg_daily_demand * metric.lead_time_days) + safety_stock
        
        # 2. Check actual stock across all bins (Available + Reserved)
        total_stock = db.query(func.sum(Inventory.qty_available + Inventory.qty_reserved)).filter(
            Inventory.product_id == metric.product_id
        ).scalar() or 0.0
        
        # 3. Evaluate if we need to order
        if total_stock <= reorder_point:
            # We need to order enough to cover lead time demand + safety stock
            suggested_qty = math.ceil(reorder_point - total_stock + (metric.avg_daily_demand * 14)) # Order 2 weeks extra
            
            # --- 4. Auto-Draft a Purchase Order (Using the NEW schema!) ---
            po_number = f"AUTO-PO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{metric.product_id}"
            
            po = PurchaseOrder(
                po_number=po_number,
                supplier_id=default_supplier.id,
                status=POStatus.DRAFT # <-- Ensure it's just a DRAFT for the manager to review
            )
            db.add(po)
            db.flush()
            
            # Use the new PurchaseOrderItem model
            po_item = PurchaseOrderItem(
                po_id=po.id, 
                product_id=metric.product_id, 
                qty_ordered=suggested_qty,
                unit_cost=0.0 # Will be updated when the PO is finalized
            )
            db.add(po_item)
            
            recommendations.append({
                "product_id": metric.product_id,
                "current_stock": total_stock,
                "reorder_point": round(reorder_point, 2),
                "suggested_order_qty": suggested_qty,
                "action_taken": f"Drafted PO {po.po_number}"
            })
            
    db.commit()
    return recommendations