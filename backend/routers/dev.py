from fastapi import APIRouter, HTTPException
from backend.services.websocket_service import manager
import logging
import asyncio

logger = logging.getLogger("Backend")
router = APIRouter()

@router.post("/dev/ai_write_patch")
async def ai_write_patch(payload: dict):
    """
    payload: {
        "session_id": str,
        "instruction": str,
        "target_range": dict (optional)
    }
    """
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
        
    try:
        # 1. Thinking
        await manager.broadcast(session_id, {"type": "ai_state", "state": "thinking", "thread_id": "ai_write"})
        await asyncio.sleep(0.5)
        
        # 2. Mock LLM Generation of Editor Ops
        # In real impl, we'd call LLM with code context.
        # Here we mock a simple replacement or insertion.
        
        ops = [
            {
                "op": "replace",
                "range": payload.get("target_range") or {"start_line": 1, "start_col": 1, "end_line": 2, "end_col": 1},
                "text": "print('AI Wrote This Patch')\n"
            }
        ]
        
        # 3. Writing
        await manager.broadcast(session_id, {"type": "ai_state", "state": "writing", "thread_id": "ai_write"})
        await asyncio.sleep(0.5)
        
        # 4. Push Editor Ops
        await manager.broadcast(session_id, {
            "type": "editor_ops",
            "ops": ops
        })
        
        # 5. Done
        await manager.broadcast(session_id, {"type": "ai_state", "state": "done", "thread_id": "ai_write"})
        
        return {"ops": ops}
        
    except Exception as e:
        await manager.broadcast(session_id, {"type": "ai_state", "state": "error", "message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))
