# src/schemas/audit.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class AuditLogResponse(BaseModel):
    id: int
    username: str
    action: str
    entity_name: str
    entity_id: int
    details: str
    timestamp: datetime
    
    model_config = {"from_attributes": True}