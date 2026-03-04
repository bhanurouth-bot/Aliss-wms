# src/api/wms.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.models import wms as models
from src.schemas import wms as schemas

# Create a router specifically for WMS operations
router = APIRouter(prefix="/wms", tags=["Warehouse Management System"])

@router.post("/warehouses/", response_model=schemas.WarehouseResponse, status_code=201)
def create_warehouse(warehouse_in: schemas.WarehouseCreate, db: Session = Depends(get_db)):
    """Create a new physical warehouse location."""
    
    # Check if a warehouse with this code already exists
    existing = db.query(models.Warehouse).filter(models.Warehouse.code == warehouse_in.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Warehouse code already exists.")
        
    # Create and save the new warehouse
    # .model_dump() converts the Pydantic schema into a dictionary (Pydantic V2 syntax)
    db_warehouse = models.Warehouse(**warehouse_in.model_dump())
    
    db.add(db_warehouse)
    db.commit()
    db.refresh(db_warehouse) # Fetch the generated ID from the database
    
    return db_warehouse

@router.get("/warehouses/", response_model=list[schemas.WarehouseResponse])
def list_warehouses(db: Session = Depends(get_db)):
    """Get all warehouses."""
    return db.query(models.Warehouse).all()

# --- ZONE ENDPOINTS ---
@router.post("/zones/", response_model=schemas.ZoneResponse, status_code=201)
def create_zone(zone_in: schemas.ZoneCreate, db: Session = Depends(get_db)):
    """Create a new zone inside an existing warehouse."""
    
    # 1. Verify the warehouse actually exists
    warehouse = db.query(models.Warehouse).filter(models.Warehouse.id == zone_in.warehouse_id).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found.")
        
    # 2. Create the zone
    db_zone = models.Zone(**zone_in.model_dump())
    db.add(db_zone)
    db.commit()
    db.refresh(db_zone)
    
    return db_zone

@router.get("/zones/", response_model=list[schemas.ZoneResponse])
def list_zones(db: Session = Depends(get_db)):
    """Get all zones."""
    return db.query(models.Zone).all()

# --- BIN ENDPOINTS ---
@router.post("/bins/", response_model=schemas.BinResponse, status_code=201)
def create_bin(bin_in: schemas.BinCreate, db: Session = Depends(get_db)):
    """Create a physical bin location inside a zone."""
    
    # 1. Verify the zone exists
    zone = db.query(models.Zone).filter(models.Zone.id == bin_in.zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found.")
        
    # 2. Check for duplicate bin codes/barcodes
    existing_bin = db.query(models.Bin).filter(
        (models.Bin.location_code == bin_in.location_code) | 
        (models.Bin.barcode == bin_in.barcode)
    ).first()
    
    if existing_bin:
        raise HTTPException(status_code=400, detail="Bin location or barcode already exists.")

    # 3. Create the bin
    db_bin = models.Bin(**bin_in.model_dump())
    db.add(db_bin)
    db.commit()
    db.refresh(db_bin)
    
    return db_bin