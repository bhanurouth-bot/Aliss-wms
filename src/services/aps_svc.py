# src/services/aps_svc.py
import math
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.models.aps import ProductMetrics
from src.models.inventory import Inventory
from src.models.purchase import PurchaseOrder, POItem

def run_replenishment_engine(db: Session):
    """Calculates Reorder Points and auto-generates Draft POs."""
    
    metrics = db.query(ProductMetrics).all()
    recommendations = []
    
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
            # (In a real ERP, we'd also factor in Economic Order Quantity (EOQ))
            suggested_qty = math.ceil(reorder_point - total_stock + (metric.avg_daily_demand * 14)) # Order 2 weeks extra
            
            # 4. Auto-Draft a Purchase Order
            po = PurchaseOrder(supplier_name="Auto-Generated Default Supplier")
            db.add(po)
            db.flush()
            
            po_item = POItem(po_id=po.id, product_id=metric.product_id, qty_ordered=suggested_qty)
            db.add(po_item)
            
            recommendations.append({
                "product_id": metric.product_id,
                "current_stock": total_stock,
                "reorder_point": round(reorder_point, 2),
                "suggested_order_qty": suggested_qty,
                "action_taken": f"Drafted PO #{po.id}"
            })
            
    db.commit()
    return recommendations