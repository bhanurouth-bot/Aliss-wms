# src/worker/celery_app.py
from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

# Load the .env file explicitly for the Celery worker
load_dotenv()

# Fetch the URL we just pasted into the .env file
RABBITMQ_URL = os.getenv("CELERY_BROKER_URL")

if not RABBITMQ_URL:
    raise ValueError("CELERY_BROKER_URL is missing! Check your .env file.")

celery_app = Celery(
    "pet_erp_worker",
    broker=RABBITMQ_URL,
    include=["src.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# --- CELERY BEAT SCHEDULE ---
celery_app.conf.beat_schedule = {
    "run-nightly-replenishment": {
        "task": "src.worker.tasks.nightly_aps_run",
        "schedule": crontab(hour=2, minute=0), 
    },
}