# src/api/purchasing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from src.core.database import get_db
from src.core.security import require_role
from src.models.purchase import Supplier, PurchaseOrder, PurchaseOrderItem, POStatus, GRN, GRNItem, SupplierProductCatalog
from src.models.inventory import Inventory, ProductBatch  # <-- Added ProductBatch here!
from src.schemas import purchasing as schemas
from src.models.wms import Bin
from src.services.order_svc import auto_cross_dock
from src.services.wms_svc import generate_warehouse_task

router = APIRouter(prefix="/purchasing", tags=["Inbound POs & Receiving (GRN)"])

@router.post("/suppliers", status_code=201)
def create_supplier(name: str, email: str, phone: str, db: Session = Depends(get_db)):
    supplier = Supplier(name=name, contact_email=email, phone=phone)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier

@router.post("/orders", response_model=schemas.POResponse, status_code=201)
def create_purchase_order(
    payload: schemas.POCreate, 
    db: Session = Depends(get_db), 
    current_user = Depends(require_role(["Admin", "Purchasing"]))
):
    """Drafts and Issues a new PO to a Supplier."""
    po_number = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    db_po = PurchaseOrder(po_number=po_number, supplier_id=payload.supplier_id, status=POStatus.ISSUED)
    db.add(db_po)
    db.flush()
    
    for item in payload.items:
        db_item = PurchaseOrderItem(
            po_id=db_po.id, product_id=item.product_id, 
            qty_ordered=item.qty_ordered, unit_cost=item.unit_cost
        )
        db.add(db_item)
        
    db.commit()
    db.refresh(db_po)
    return db_po

@router.post("/orders/{po_id}/receive")
def receive_po_and_generate_grn(
    po_id: int, 
    payload: schemas.GRNCreateRequest, 
    db: Session = Depends(get_db), 
    current_user = Depends(require_role(["Admin", "Warehouse Staff"]))
):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found.")
    
    if po.status == POStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="This PO is already completely received.")

    scanned_totals = {}
    for item in payload.scanned_items:
        scanned_totals[item.product_id] = scanned_totals.get(item.product_id, 0) + item.qty_received

        # --- STRICT BIN VALIDATION! ---
        bin_record = db.query(Bin).filter(Bin.id == item.bin_id).first()
        if not bin_record:
            raise HTTPException(status_code=400, detail=f"Invalid location! Bin ID {item.bin_id} does not exist in the warehouse.")

    for prod_id, scan_qty in scanned_totals.items():
        po_item = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.po_id == po.id, PurchaseOrderItem.product_id == prod_id
        ).first()
        
        if not po_item:
            raise HTTPException(status_code=400, detail=f"Product ID {prod_id} is NOT on this PO! Reject the item from the truck.")
        
        remaining_expected = po_item.qty_ordered - po_item.qty_received
        if scan_qty > remaining_expected:
            raise HTTPException(status_code=400, detail=f"Over-shipment detected for Product ID {prod_id}! Expected {remaining_expected}, Scanned {scan_qty}. Send the extra items back!")

    grn_number = f"GRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    db_grn = GRN(grn_number=grn_number, po_id=po.id, notes=payload.notes, received_by=current_user.id)
    db.add(db_grn)
    db.flush()

    cross_dock_alerts = [] # To hold our alerts!

    for item in payload.scanned_items:
        po_item = db.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.po_id == po.id, PurchaseOrderItem.product_id == item.product_id
        ).first()
        po_item.qty_received += item.qty_received

        db_grn_item = GRNItem(
            grn_id=db_grn.id, product_id=item.product_id, 
            qty_received=item.qty_received, bin_id=item.bin_id
        )
        db.add(db_grn_item)

        # --- NEW: DYNAMIC BATCH CREATION ---
        actual_batch_id = None
        
        if getattr(item, 'batch_number', None):
            # Check if this batch already exists in the warehouse
            existing_batch = db.query(ProductBatch).filter(
                ProductBatch.product_id == item.product_id,
                ProductBatch.batch_number == item.batch_number
            ).first()
            
            if existing_batch:
                actual_batch_id = existing_batch.id
            else:
                # Create a brand new batch from the manufacturer!
                new_batch = ProductBatch(
                    product_id=item.product_id,
                    batch_number=item.batch_number,
                    expiry_date=item.expiry_date
                )
                db.add(new_batch)
                db.flush() # Get the new batch ID
                actual_batch_id = new_batch.id

        # --- UPDATED INVENTORY LOGIC ---
        inventory = db.query(Inventory).filter(
            Inventory.product_id == item.product_id,
            Inventory.bin_id == item.bin_id,
            Inventory.batch_id == actual_batch_id
        ).first()

        if inventory:
            inventory.qty_available += item.qty_received
        else:
            new_inv = Inventory(
                product_id=item.product_id, 
                bin_id=item.bin_id, 
                batch_id=actual_batch_id, 
                qty_available=item.qty_received
            )
            db.add(new_inv)

        # --- TRIGGER THE CROSS-DOCK ENGINE! ---
        cross_docked_orders = auto_cross_dock(db, product_id=item.product_id)
        if cross_docked_orders:
            cross_dock_alerts.append(f"🚨 CROSS-DOCK ALERT! {item.qty_received} units of Product {item.product_id} immediately routed to fulfill Orders: {cross_docked_orders}. Skip put-away and take items directly to Packing Desk!")

    po_items = db.query(PurchaseOrderItem).filter(PurchaseOrderItem.po_id == po.id).all()
    po_fully_received = all(i.qty_received >= i.qty_ordered for i in po_items)

    po.status = POStatus.COMPLETED if po_fully_received else POStatus.PARTIAL_RECEIVED

    if not cross_docked_orders:
            generate_warehouse_task(
                db=db,
                task_type="GRN_PUTAWAY",
                product_id=item.product_id,
                bin_id=item.bin_id, # This is the Loading Dock Bin
                qty_expected=item.qty_received,
                priority=1, # Normal priority putaway
                batch_id=actual_batch_id,
                target_time_seconds=600 # 10 mins for forklift driver
            )

    db.commit()
    db.refresh(db_grn)
    
    return {
        "message": "Receiving verified. GRN legally created and Physical Inventory updated.",
        "grn_number": db_grn.grn_number,
        "new_po_status": po.status.name,
        "cross_dock_alerts": cross_dock_alerts # Show the worker the flashing alerts!
    }

@router.post("/suppliers/{supplier_id}/catalog", response_model=schemas.CatalogItemResponse)
def add_product_to_supplier_catalog(
    supplier_id: int, 
    payload: schemas.CatalogItemCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Purchasing"]))
):
    """
    Registers a contract with a supplier for a specific product, locking in 
    the unit cost, Minimum Order Quantity (MOQ), and Lead Time.
    """
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
        
    # If this is marked as primary, unmark any other primary suppliers for this product
    if payload.is_primary:
        existing_primaries = db.query(SupplierProductCatalog).filter(
            SupplierProductCatalog.product_id == payload.product_id,
            SupplierProductCatalog.is_primary == True
        ).all()
        for ep in existing_primaries:
            ep.is_primary = False

    catalog_entry = SupplierProductCatalog(
        supplier_id=supplier.id,
        product_id=payload.product_id,
        negotiated_unit_cost=payload.negotiated_unit_cost,
        minimum_order_qty=payload.minimum_order_qty,
        lead_time_days=payload.lead_time_days,
        is_primary=payload.is_primary
    )
    
    db.add(catalog_entry)
    db.commit()
    db.refresh(catalog_entry)
    return catalog_entry

# --- VIEW SUPPLIERS ---
@router.get("/suppliers", response_model=List[schemas.SupplierResponse])
def get_all_suppliers(
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Purchasing", "Warehouse Manager"]))
):
    """View a list of all registered suppliers."""
    return db.query(Supplier).all()


# --- VIEW SUPPLIER CATALOG ---
@router.get("/suppliers/{supplier_id}/catalog", response_model=List[schemas.CatalogItemResponse])
def get_supplier_catalog(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Purchasing"]))
):
    """View all products, negotiated prices, and MOQs linked to a specific supplier."""
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
        
    return db.query(SupplierProductCatalog).filter(SupplierProductCatalog.supplier_id == supplier.id).all()


# --- VIEW ALL PURCHASE ORDERS ---
@router.get("/orders", response_model=List[schemas.POResponse])
def get_all_purchase_orders(
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Purchasing", "Warehouse Manager", "Warehouse Staff"]))
):
    """View all drafted, issued, and completed Purchase Orders."""
    return db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).all()


# --- VIEW A SPECIFIC PURCHASE ORDER ---
@router.get("/orders/{po_id}", response_model=schemas.POResponse)
def get_purchase_order_by_id(
    po_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_role(["Admin", "Purchasing", "Warehouse Manager", "Warehouse Staff"]))
):
    """View the exact details and items of a specific PO."""
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found.")
    return po