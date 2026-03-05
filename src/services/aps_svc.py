# src/services/aps_svc.py
import math
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.models.aps import ProductMetrics
from src.models.inventory import Inventory
from src.models.purchase import PurchaseOrder, PurchaseOrderItem, Supplier, POStatus, SupplierProductCatalog

def run_replenishment_engine(db: Session):
    """Calculates Reorder Points and auto-generates Draft POs based on Supplier Contracts."""
    
    metrics = db.query(ProductMetrics).all()
    recommendations = []

    for metric in metrics:
        # --- 1. FIND THE SUPPLIER CONTRACT ---
        catalog_entry = db.query(SupplierProductCatalog).filter(
            SupplierProductCatalog.product_id == metric.product_id,
            SupplierProductCatalog.is_primary == True
        ).first()

        if not catalog_entry:
            # We can't auto-order if we don't know who sells it to us!
            continue 

        # --- 2. THE MATHEMATICS (Using Real Supplier Lead Time!) ---
        lead_time = catalog_entry.lead_time_days
        safety_stock = metric.service_level_z_score * metric.demand_std_dev * math.sqrt(lead_time)
        reorder_point = (metric.avg_daily_demand * lead_time) + safety_stock
        
        # Check actual stock across all bins
        total_stock = db.query(func.sum(Inventory.qty_available + Inventory.qty_reserved)).filter(
            Inventory.product_id == metric.product_id
        ).scalar() or 0.0
        
        # --- 3. EVALUATE & ENFORCE MOQ ---
        if total_stock <= reorder_point:
            # We need enough to cover the lead time + safety + 2 weeks buffer
            needed_qty = math.ceil(reorder_point - total_stock + (metric.avg_daily_demand * 14))
            
            # If we need 40, but the Supplier's Minimum Order Qty is 100, we MUST order 100.
            suggested_qty = max(needed_qty, catalog_entry.minimum_order_qty)
            
            # --- 4. DRAFT THE INTELLIGENT PO ---
            po_number = f"AUTO-PO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{metric.product_id}"
            
            po = PurchaseOrder(
                po_number=po_number,
                supplier_id=catalog_entry.supplier_id,
                status=POStatus.DRAFT # Keeps it as a draft for manager approval
            )
            db.add(po)
            db.flush()
            
            po_item = PurchaseOrderItem(
                po_id=po.id, 
                product_id=metric.product_id, 
                qty_ordered=suggested_qty,
                unit_cost=catalog_entry.negotiated_unit_cost # <-- WE NOW USE THE REAL COST!
            )
            db.add(po_item)
            
            recommendations.append({
                "product_id": metric.product_id,
                "supplier_id": catalog_entry.supplier_id,
                "current_stock": total_stock,
                "reorder_point": round(reorder_point, 2),
                "suggested_order_qty": suggested_qty,
                "unit_cost": catalog_entry.negotiated_unit_cost,
                "action_taken": f"Drafted PO {po.po_number}"
            })
            
    db.commit()
    return recommendations