# src/schemas/audit.py
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime

class AuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    before_data: Optional[Dict[str, Any]]
    after_data: Optional[Dict[str, Any]]
    performed_by: Optional[int]
    timestamp: datetime
    ip_address: Optional[str]

    model_config = {"from_attributes": True}