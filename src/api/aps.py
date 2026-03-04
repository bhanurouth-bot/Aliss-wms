# src/api/aps.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from src.core.database import get_db
from src.models.aps import ProductMetrics
from src.schemas import aps as schemas
from src.services.aps_svc import run_replenishment_engine
from src.worker.tasks import nightly_aps_run

router = APIRouter(prefix="/aps", tags=["APS & Replenishment"])

@router.post("/metrics/", response_model=schemas.ProductMetricsCreate)
def set_product_metrics(metrics_in: schemas.ProductMetricsCreate, db: Session = Depends(get_db)):
    """Set the historical demand metrics for a product."""
    db_metric = ProductMetrics(**metrics_in.model_dump())
    db.add(db_metric)
    db.commit()
    return db_metric

@router.post("/run-engine/", response_model=List[schemas.ReplenishmentRecommendation])
def trigger_replenishment(db: Session = Depends(get_db)):
    """Run the APS engine to check stock levels and auto-draft POs."""
    return run_replenishment_engine(db)

@router.post("/run-engine/async")
def trigger_replenishment_async():
    """Drop a message in RabbitMQ to run the engine in the background."""
    
    # .delay() is the Celery magic command. 
    # It sends the task to RabbitMQ and instantly returns control to FastAPI.
    task = nightly_aps_run.delay() 
    
    return {
        "message": "APS Engine has been queued in the background.",
        "task_id": task.id
    }