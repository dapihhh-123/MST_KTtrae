from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.services.websocket_service import manager
from backend.services.telemetry import telemetry_service
import asyncio
from typing import Dict, Any, List

router = APIRouter()

@router.post("/debug/push_test")
async def push_test(payload: Dict[str, Any] = Body(...)):
    # ... existing implementation (kept for compatibility) ...
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required")

    await manager.broadcast(session_id, {
        "type": "ai_state",
        "state": "thinking",
        "scope": "global",
        "thread_id": "debug_thread"
    })
    await asyncio.sleep(1)

    await manager.broadcast(session_id, {
        "type": "highlight_spans",
        "spans": [{"line_start": 10, "line_end": 15, "score": 0.95}],
        "ttl_ms": 5000
    })
    await asyncio.sleep(1)

    chunks = ["This is ", "a debug ", "message."]
    message_id = "debug_msg_1"
    
    await manager.broadcast(session_id, {
        "type": "ai_state",
        "state": "writing",
        "scope": "global",
        "thread_id": "debug_thread"
    })

    for i, chunk in enumerate(chunks):
        await manager.broadcast(session_id, {
            "type": "ai_text_chunk",
            "thread_id": "debug_thread",
            "message_id": message_id,
            "delta": chunk,
            "seq": i,
            "is_final": False
        })
        await asyncio.sleep(0.5)

    await manager.broadcast(session_id, {
        "type": "ai_text_chunk",
        "thread_id": "debug_thread",
        "message_id": message_id,
        "delta": "",
        "seq": len(chunks),
        "is_final": True
    })
    await manager.broadcast(session_id, {
        "type": "ai_state",
        "state": "done",
        "scope": "global",
        "thread_id": "debug_thread"
    })

    return {"status": "ok", "message": "Pushed debug sequence"}

# --- New Debug Endpoints ---

@router.get("/debug/trace")
def debug_trace(trace_id: str, db: Session = Depends(get_db)):
    events = db.query(models.EventLog).filter(models.EventLog.trace_id == trace_id).all()
    diagnoses = db.query(models.DiagnosisLog).filter(models.DiagnosisLog.trace_id == trace_id).all()
    
    return {
        "trace_id": trace_id,
        "events": [e.id for e in events],
        "diagnoses": [d.id for d in diagnoses],
        "event_count": len(events),
        "diagnosis_count": len(diagnoses)
    }

@router.get("/debug/event/{event_id}")
def debug_event(event_id: str, db: Session = Depends(get_db)):
    event = db.query(models.EventLog).filter(models.EventLog.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    code_state = None
    if event.code_state_id:
        code_state = db.query(models.CodeState).filter(models.CodeState.id == event.code_state_id).first()
        
    return {
        "event_id": event.id,
        "type": event.type,
        "trace_id": event.trace_id,
        "code_state_id": event.code_state_id,
        "code_state_hash": code_state.content_hash if code_state else None
    }

@router.get("/debug/code_state/{code_state_id}")
def debug_code_state(code_state_id: str, db: Session = Depends(get_db)):
    cs = db.query(models.CodeState).filter(models.CodeState.id == code_state_id).first()
    if not cs:
        raise HTTPException(status_code=404, detail="CodeState not found")
        
    return {
        "id": cs.id,
        "content_hash": cs.content_hash,
        "content_preview": "\n".join(cs.content.split("\n")[:10]) if cs.content else ""
    }

@router.get("/debug/telemetry")
def debug_telemetry(session_id: str):
    return telemetry_service.get_metrics(session_id)
