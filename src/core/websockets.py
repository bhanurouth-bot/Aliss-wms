# src/core/websockets.py
import asyncio
import json
import redis.asyncio as aioredis
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        """Send a message to all connected browsers."""
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

async def listen_to_redis_pubsub(redis_url: str):
    """
    Background task that listens to the Redis channel.
    """
    clean_url = redis_url.strip(' \'"\r\n')
    
    kwargs = {}
    if clean_url.startswith("rediss://"):
        # We just use the standard argument now that the URL is correct!
        kwargs["ssl_cert_reqs"] = "none"
        
    redis = aioredis.from_url(clean_url, **kwargs)
    
    pubsub = redis.pubsub()
    await pubsub.subscribe("erp_notifications")
    
    print("🎧 Listening for Redis ERP Notifications...")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await manager.broadcast(data)