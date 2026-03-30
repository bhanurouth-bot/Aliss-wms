# src/core/middleware.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import jwt

from src.core.config import settings
from src.worker.tasks import async_write_audit_log  # <-- Import the Celery task

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
                # 3. Dispatch the audit log to the Celery queue asynchronously!
                async_write_audit_log.delay(
                    username=username,
                    method=request.method,
                    path=path,
                    status_code=response.status_code
                )

        return response