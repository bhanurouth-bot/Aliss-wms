# src/main.py (Update imports and include_router)
from fastapi import FastAPI
from src.core.database import engine, Base

from src.models import wms, product, inventory, order, wms_ops, purchase, aps, audit, manufacturing, auth, billing

# Import routers
from src.api import wms as wms_api
from src.api import products as products_api
from src.api import inventory as inventory_api
from src.api import orders as orders_api
from src.api import wms_ops as wms_ops_api
from src.api import aps as aps_api 
from src.api import audit as audit_api 
from src.api import manufacturing as manufacturing_api
from src.api import auth as auth_api
from src.api import integrations as integrations_api 
from src.api import billing as billing_api
# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Pet Products ERP API",
    description="Enterprise Backend for WMS, APS, and Order Management",
    version="1.0.0"
)

# Include routers
app.include_router(wms_api.router)
app.include_router(products_api.router)
app.include_router(inventory_api.router)
app.include_router(orders_api.router)  
app.include_router(wms_ops_api.router)
app.include_router(aps_api.router)
app.include_router(audit_api.router)
app.include_router(manufacturing_api.router)
app.include_router(auth_api.router)
app.include_router(billing_api.router)
app.include_router(integrations_api.router)

@app.get("/health")
def health_check():
    return {"status": "online", "database": "SQLite connected."}