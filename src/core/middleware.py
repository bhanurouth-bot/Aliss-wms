# src/core/middleware.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.background import BackgroundTask # <-- Import BackgroundTask
import jwt

from src.core.database import SessionLocal
from src.core.config import settings
from src.services.audit_svc import log_activity

def write_audit_log_in_background(username: str, method: str, path: str, status_code: int):
    """
    This function runs in the background AFTER the main request is completely finished
    and the primary database connection has been closed. This prevents SQLite locks!
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
    finally:
        db.close()

class GlobalAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Let the request pass through to your endpoints
        response = await call_next(request)

        # 2. We only want to log state-changing actions
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            
            username = "System/Anonymous"
            auth_header = request.headers.get("Authorization")
            
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                try:
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                    username = payload.get("sub", username)
                except Exception:
                    pass 

            path = request.url.path
            
            # We skip logging the login/register endpoints
            if "/auth/" not in path:
                # 3. Attach the audit log as a background task to the response!
                response.background = BackgroundTask(
                    write_audit_log_in_background,
                    username=username,
                    method=request.method,
                    path=path,
                    status_code=response.status_code
                )

        return response