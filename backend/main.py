from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import sys
from backend import models
from backend.database import engine
from backend.routers import chat, project, diagnose, events, agent, selfcheck, debug, dev, llm_api, runner
from backend.services.websocket_service import manager

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Backend")

# Create DB Tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Collaborative Coding Backend", description="Realtime collaboration API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(project.router, prefix="/api", tags=["project"])
app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
app.include_router(selfcheck.router, prefix="/api", tags=["selfcheck"])
app.include_router(debug.router, prefix="/api", tags=["debug"])
app.include_router(dev.router, prefix="/api", tags=["dev"])
app.include_router(llm_api.router, prefix="/api", tags=["llm"])
app.include_router(runner.router, prefix="/api", tags=["runner"])
app.include_router(diagnose.router, tags=["diagnose"]) # Keep root /diagnose for backward compat or move to /api

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}

@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo for testing or handle client messages
            # For now, just keep alive and echo back to session
            # await manager.broadcast(session_id, {"type": "echo", "payload": data})
            pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
