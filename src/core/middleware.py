# src/core/middleware.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import jwt

from src.core.database import SessionLocal
from src.core.config import settings
from src.services.audit_svc import log_activity

class GlobalAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Let the request pass through to your endpoints
        response = await call_next(request)

        # 2. We only want to log state-changing actions (Ignore GET and OPTIONS)
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            
            # Extract the user from the JWT Token in the headers
            username = "System/Anonymous"
            auth_header = request.headers.get("Authorization")
            
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                try:
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                    username = payload.get("sub", username)
                except Exception:
                    pass # Invalid or expired token

            # 3. Save the log to the database
            db = SessionLocal()
            try:
                path = request.url.path
                
                # We skip logging the login/register endpoints to avoid clutter
                if "/auth/" not in path:
                    log_activity(
                        db=db,
                        username=username,
                        action=request.method,
                        entity=path, # We use the URL path as the entity!
                        entity_id=0, # We don't know the exact DB ID globally
                        details=f"Global API Audit: {request.method} {path} resulted in HTTP {response.status_code}"
                    )
            finally:
                db.close()

        return response