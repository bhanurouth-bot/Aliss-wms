# src/services/wms_svc.py
from sqlalchemy.orm import Session
from src.models.wms_ops import Picklist, PickTask
from fastapi import HTTPException
from src.models.wms_ops import TaskStatus
from src.models.wms import Bin
from src.models.product import Product
from src.models.inventory import Inventory
from src.models.order import Order, OrderStatus
from sqlalchemy import func
from src.worker.tasks import send_inventory_webhook

def generate_picklist(db: Session, order_id: int, allocations: list):
    """
    Takes the FEFO inventory allocations and generates physical pick tasks.
    """
    picklist = Picklist(order_id=order_id)
    db.add(picklist)
    db.flush() # Get the picklist ID immediately

    for alloc in allocations:
        task = PickTask(
            picklist_id=picklist.id,
            product_id=alloc['product_id'],
            bin_id=alloc['bin_id'],
            batch_id=alloc['batch_id'],
            qty_expected=alloc['qty']
        )
        db.add(task)
        
    db.flush()
    return picklist

def confirm_pick_task(db: Session, task_id: int, scanned_bin: str, scanned_product: str, qty_picked: float):
    # 1. Fetch the exact task
    task = db.query(PickTask).filter(PickTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    
    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="This task is already completed.")

    # 2. Fetch the physical entities to verify barcodes
    bin_record = db.query(Bin).filter(Bin.id == task.bin_id).first()
    product = db.query(Product).filter(Product.id == task.product_id).first()

    # 3. THE SCANNER VALIDATION (Crucial for preventing shipping errors)
    if bin_record.barcode != scanned_bin:
        raise HTTPException(status_code=400, detail=f"Wrong Bin! Expected {bin_record.location_code}")
        
    if product.barcode != scanned_product:
        raise HTTPException(status_code=400, detail=f"Wrong Product! Expected {product.sku}")

    if qty_picked + task.qty_picked > task.qty_expected:
        raise HTTPException(status_code=400, detail="Cannot over-pick. You are scanning too many items.")

    # 4. Update the Task
    task.qty_picked += qty_picked
    if task.qty_picked == task.qty_expected:
        task.status = TaskStatus.COMPLETED
    else:
        task.status = TaskStatus.IN_PROGRESS

    # 5. Permanently remove the stock from the Bin's Reserved pool
    # (Remember, we already deducted it from 'Available' when the order was placed)
    inventory = db.query(Inventory).filter(
        Inventory.product_id == task.product_id,
        Inventory.bin_id == task.bin_id,
        Inventory.batch_id == task.batch_id
    ).first()
    
    if inventory:
        inventory.qty_reserved -= qty_picked
        # If the bin is now completely empty (0 available, 0 reserved), we could optionally delete the record or leave it at 0.

    # 6. Check if the entire Picklist is now finished
    picklist = db.query(Picklist).filter(Picklist.id == task.picklist_id).first()
    all_tasks = db.query(PickTask).filter(PickTask.picklist_id == picklist.id).all()
    
    if all(t.status == TaskStatus.COMPLETED for t in all_tasks):
        picklist.status = TaskStatus.COMPLETED
        
        # Advance the Order status to PROCESSING (meaning it's ready to be boxed and shipped)
        order = db.query(Order).filter(Order.id == picklist.order_id).first()
        if order:
            order.status = OrderStatus.PROCESSING

    db.commit()
    db.refresh(task)
    
    # --- NEW: TRIGGER REAL-TIME WEBSITE SYNC ---
    # Calculate the total available stock for this product across the whole warehouse
    total_available = db.query(func.sum(Inventory.qty_available)).filter(
        Inventory.product_id == task.product_id
    ).scalar() or 0.0
    
    # Drop the message into RabbitMQ so Celery can send it in the background!
    send_inventory_webhook.delay(product_id=task.product_id, new_available_qty=total_available)

    return task