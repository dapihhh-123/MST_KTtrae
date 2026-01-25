from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import logging

logger = logging.getLogger("Backend")

class ConnectionManager:
    def __init__(self):
        # Map session_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
        logger.info(f"WS Connected: {session_id} (Total: {len(self.active_connections[session_id])})")

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
            logger.info(f"WS Disconnected: {session_id}")

    async def broadcast(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            # Copy to avoid runtime error if set changes during iteration
            for connection in list(self.active_connections[session_id]):
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"WS Send Error: {e}")
                    # Could remove dead connection here
                    
    async def broadcast_global(self, message: dict):
        """Broadcast to ALL sessions (for system alerts etc)"""
        for sid in self.active_connections:
            await self.broadcast(sid, message)

manager = ConnectionManager()
