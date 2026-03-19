# src/services/wms_svc.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import func

from src.models.wms_ops import WarehouseTask, PickingWave, TaskStatus 
from src.models.wms import Bin
from src.models.product import Product
from src.models.inventory import Inventory
from src.models.order import Order, OrderStatus
from src.worker.tasks import send_inventory_webhook


def confirm_pick_task(
    db: Session, 
    task_id: int, 
    scanned_bin: str, 
    scanned_product: str, 
    qty_picked: float,
    worker_id: int
):
    # 1. Fetch the exact task
    task = db.query(WarehouseTask).filter(WarehouseTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    
    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="This task is already completed.")

    # 2. Fetch the physical entities to verify barcodes
    bin_record = db.query(Bin).filter(Bin.id == task.bin_id).first()
    product = db.query(Product).filter(Product.id == task.product_id).first()

    # 3. THE SCANNER VALIDATION
    if bin_record.barcode != scanned_bin:
        raise HTTPException(status_code=400, detail=f"Wrong Bin! Expected {bin_record.location_code}")
        
    if product.barcode != scanned_product:
        raise HTTPException(status_code=400, detail=f"Wrong Product! Expected {product.sku}")

    if qty_picked + task.qty_picked > task.qty_expected:
        raise HTTPException(status_code=400, detail="Cannot over-pick. You are scanning too many items.")

    # 4. Update the Task with Worker Accountability
    task.qty_picked += qty_picked
    task.worker_id = worker_id

    if task.qty_picked >= task.qty_expected: 
        task.status = TaskStatus.COMPLETED
        task.completed_at = func.now()
    else:
        task.status = TaskStatus.IN_PROGRESS

    db.flush() 

    # 5. Permanently remove the stock from the Bin's Reserved pool
    inventory = db.query(Inventory).filter(
        Inventory.product_id == task.product_id,
        Inventory.bin_id == task.bin_id,
        Inventory.batch_id == task.batch_id
    ).first()
    
    if inventory:
        inventory.qty_reserved -= qty_picked

    # --- 6. CHECK IF THE PARENT (ORDER OR WAVE) IS FINISHED ---
    if task.order_id:
        # Ask the DB: Are there any tasks for this order that are NOT completed?
        incomplete_tasks = db.query(WarehouseTask).filter(
            WarehouseTask.order_id == task.order_id,
            WarehouseTask.status != TaskStatus.COMPLETED
        ).count()
        
        if incomplete_tasks == 0:
            order = db.query(Order).filter(Order.id == task.order_id).first()
            if order:
                order.status = OrderStatus.CHECKING

    elif task.wave_id:
        # Ask the DB: Are there any tasks for this wave that are NOT completed?
        incomplete_tasks = db.query(WarehouseTask).filter(
            WarehouseTask.wave_id == task.wave_id,
            WarehouseTask.status != TaskStatus.COMPLETED
        ).count()
        
        if incomplete_tasks == 0:
            wave = db.query(PickingWave).filter(PickingWave.id == task.wave_id).first()
            if wave:
                wave.status = TaskStatus.COMPLETED
                
                # Auto-update ALL orders inside this wave to CHECKING
                for order in wave.orders:
                    order.status = OrderStatus.CHECKING

    db.commit()
    db.refresh(task)
    
    # 7. TRIGGER REAL-TIME WEBSITE SYNC
    total_available = db.query(func.sum(Inventory.qty_available)).filter(
        Inventory.product_id == task.product_id
    ).scalar() or 0.0
    
    send_inventory_webhook.delay(product_id=task.product_id, new_available_qty=total_available)

    return task