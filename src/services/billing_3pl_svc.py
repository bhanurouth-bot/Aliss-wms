# src/services/billing_3pl_svc.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from src.models.inventory import Inventory
from src.models.product import Product
from src.models.third_party import ClientStorageLog

def snapshot_daily_storage(db: Session, target_date: date):
    """Calculates the total cubic footage occupied by every 3PL client at midnight."""
    
    # 1. Join Inventory with Product to get dimensions and ownership
    client_inventory = (
        db.query(
            Product.client_id,
            func.sum(Inventory.qty_available * (Product.length * Product.width * Product.height)).label("total_volume_inches")
        )
        .join(Inventory, Inventory.product_id == Product.id)
        .group_by(Product.client_id)
        .all()
    )
    
    logs_created = []
    
    # 2. Convert to Cubic Feet and Log the Financial Charge
    for client_id, total_volume_inches in client_inventory:
        if not client_id or not total_volume_inches:
            continue
            
        # 1728 cubic inches in a cubic foot
        total_cubic_feet = round(total_volume_inches / 1728, 2)
        rate_per_cuft = 0.05 # You could make this dynamic per client!
        daily_fee = round(total_cubic_feet * rate_per_cuft, 2)
        
        log = ClientStorageLog(
            client_id=client_id,
            record_date=target_date,
            total_cubic_feet=total_cubic_feet,
            storage_rate_per_cuft=rate_per_cuft,
            daily_fee=daily_fee
        )
        db.add(log)
        logs_created.append(log)
        
    db.commit()
    return logs_created