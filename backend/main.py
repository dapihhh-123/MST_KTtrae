from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import sys
import os
from backend import models
from backend.database import engine
from backend.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, KEY_FINGERPRINT, DOTENV_PATH, ENV_LOADED
# from backend.routers import chat, project, diagnose, events, agent, selfcheck, debug, dev, llm_api, runner
from backend.routers import chat, project, diagnose, agent, selfcheck, debug, dev, llm_api, runner, oracle, psw_telemetry
from backend.services.websocket_service import manager

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Backend")

# 1.2 Startup Log
# Force print to ensure capture in log file
print(f"[CFG] OPENAI_KEY_PRESENT={KEY_FINGERPRINT['present']} OPENAI_KEY_PREFIX={KEY_FINGERPRINT['prefix']} OPENAI_KEY_SHA256_8={KEY_FINGERPRINT['sha256_8']} OPENAI_BASE_URL={OPENAI_BASE_URL} ENV_SOURCE={'dotenv' if ENV_LOADED else 'osenv'}", flush=True)
print(f"[CFG] DOTENV_PATH_USED={DOTENV_PATH}", flush=True)

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
# app.include_router(events.router, prefix="/api", tags=["events"])
app.include_router(agent.router, prefix="/api", tags=["agent"])
app.include_router(selfcheck.router, prefix="/api", tags=["selfcheck"])
app.include_router(debug.router, prefix="/api", tags=["debug"])
app.include_router(dev.router, prefix="/api", tags=["dev"])
app.include_router(llm_api.router, prefix="/api", tags=["llm"])
app.include_router(runner.router, prefix="/api", tags=["runner"])
app.include_router(oracle.router, prefix="/api", tags=["oracle"]) # Added oracle
app.include_router(psw_telemetry.router, prefix="/api", tags=["psw-telemetry"])
app.include_router(diagnose.router, tags=["diagnose"]) # Keep root /diagnose for backward compat or move to /api

@app.on_event("startup")
async def startup_event():
    # Force print to ensure capture in log file
    print(f"[CFG] OPENAI_KEY_PRESENT={KEY_FINGERPRINT['present']} OPENAI_KEY_PREFIX={KEY_FINGERPRINT['prefix']} OPENAI_KEY_SHA256_8={KEY_FINGERPRINT['sha256_8']} OPENAI_BASE_URL={OPENAI_BASE_URL} ENV_SOURCE={'dotenv' if ENV_LOADED else 'osenv'}", flush=True)
    print(f"[CFG] DOTENV_PATH_USED={DOTENV_PATH}", flush=True)

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
    # Force print to ensure capture in log file (Startup Proof)
    print(f"[CFG] OPENAI_KEY_PRESENT={KEY_FINGERPRINT['present']} OPENAI_KEY_PREFIX={KEY_FINGERPRINT['prefix']} OPENAI_KEY_SHA256_8={KEY_FINGERPRINT['sha256_8']} OPENAI_BASE_URL={OPENAI_BASE_URL} ENV_SOURCE={'dotenv' if ENV_LOADED else 'osenv'}", flush=True)
    print(f"[CFG] DOTENV_PATH_USED={DOTENV_PATH}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8001)
