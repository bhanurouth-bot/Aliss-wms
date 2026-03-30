# src/worker/tasks.py
import logging
import requests
import json
import os
import redis # <-- Added redis import
from src.worker.celery_app import celery_app
from src.core.database import SessionLocal
from src.services.aps_svc import run_replenishment_engine
from src.services.audit_svc import log_activity

# The URL of your e-commerce storefront's API
WEBSITE_WEBHOOK_URL = "https://your-website.com/api/webhooks/erp-sync"
WEBHOOK_SECRET = "super_secret_webhook_key_to_prove_its_the_erp"

logger = logging.getLogger(__name__)

# --- NEW: Initialize a synchronous Redis client for the worker ---
# --- Safely Initialize Redis Client ---
_raw_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
if _raw_redis_url:
    _raw_redis_url = _raw_redis_url.strip(' \'"\r\n')

if not _raw_redis_url or not _raw_redis_url.startswith(("redis://", "rediss://", "unix://")):
    _raw_redis_url = "redis://localhost:6379/0"

_redis_kwargs = {}
if _raw_redis_url.startswith("rediss://"):
    _redis_kwargs["ssl_cert_reqs"] = "none"

redis_client = redis.Redis.from_url(_raw_redis_url, **_redis_kwargs)
# -----------------------------------------------------

@celery_app.task(bind=True, max_retries=3)
def async_write_audit_log(self, username: str, method: str, path: str, status_code: int):
    """
    Background task to write audit logs via Celery Queue.
    This prevents the main FastAPI app from exhausting database connections.
    """
    db = SessionLocal()
    try:
        log_activity(
            db=db,
            username=username,
            action=method,
            entity=path,
            entity_id=0,
            details=f"Global API Audit: {method} {path} resulted in HTTP {status_code}"
        )
    except Exception as e:
        logger.error(f"Failed to write audit log: {str(e)}")
        db.rollback()
        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()

@celery_app.task(bind=True, max_retries=3)
def nightly_aps_run(self):
    """
    Background task to run the APS Replenishment Engine.
    It opens its own database session since it runs completely separately from FastAPI.
    """
    logger.info("Starting Nightly APS Replenishment Engine...")
    
    # Create a fresh database session for the background worker
    db = SessionLocal()
    try:
        # Run the exact same engine we built earlier!
        recommendations = run_replenishment_engine(db)
        
        # --- NEW: SEND WEBSOCKET NOTIFICATION ---
        alert_payload = {
            "type": "APS_RUN_COMPLETE",
            "message": f"Nightly replenishment finished. Generated {len(recommendations)} PO actions."
        }
        # Publish to the channel FastAPI is listening to!
        redis_client.publish("erp_notifications", json.dumps(alert_payload))
        # ----------------------------------------
        
        logger.info(f"APS Engine Complete. Generated {len(recommendations)} PO actions.")
        return {"status": "success", "actions_taken": len(recommendations)}
        
    except Exception as e:
        logger.error(f"Error running APS Engine: {str(e)}")
        db.rollback()
        # If the database locks or fails, tell Celery to retry the task in 60 seconds
        raise self.retry(exc=e, countdown=60)
        
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def send_inventory_webhook(self, product_id: int, new_available_qty: float):
    """
    Sends a real-time HTTP POST to your e-commerce website 
    to update the available stock counter.
    """
    payload = {
        "product_id": product_id,
        "available_qty": new_available_qty,
        "source": "PET_ERP"
    }
    
    headers = {
        "Authorization": f"Bearer {WEBHOOK_SECRET}",
        "Content-Type": "application/json"
    }
    
    try:
        # Send the payload to the website
        response = requests.post(WEBSITE_WEBHOOK_URL, json=payload, headers=headers, timeout=5)
        response.raise_for_status() # Raises an error if the website returns 500 or 404
        
        logger.info(f"Successfully synced Product {product_id} to website. New Qty: {new_available_qty}")
        return {"status": "synced", "product_id": product_id}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to sync with website: {str(e)}")
        # If the website is down, retry the task in 30 seconds!
        raise self.retry(exc=e)
    

@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def send_shipping_webhook(self, external_reference: str, carrier: str, tracking_number: str):
    """
    Tells the external storefront (Amazon/Shopify) that the order has shipped.
    """
    payload = {
        "order_id": external_reference,
        "status": "SHIPPED",
        "carrier": carrier,
        "tracking_number": tracking_number
    }
    
    headers = {
        "Authorization": f"Bearer {WEBHOOK_SECRET}",
        "Content-Type": "application/json"
    }
    
    try:
        # Pushing the tracking info back to the website
        response = requests.post(f"{WEBSITE_WEBHOOK_URL}/shipments", json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        
        logger.info(f"Successfully notified external platform for Order {external_reference}. Tracking: {tracking_number}")
        return {"status": "success", "tracking": tracking_number}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send shipping webhook: {str(e)}")
        raise self.retry(exc=e)