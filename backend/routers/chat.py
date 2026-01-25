from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import schemas, models, utils
from backend.services.websocket_service import manager
from backend.services.chat_service import ChatService
from backend.services.llm_service import llm_service
from backend.services.prompting import build_chat_messages
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import time

router = APIRouter()

# Rate Limiting Cache (Simple in-memory for MVP)
# Key: thread_id, Value: timestamp of last request
_rate_limit_store = {}

@router.get("/threads", response_model=List[schemas.Thread])
def get_threads(session_id: str, db: Session = Depends(get_db)):
    service = ChatService(db)
    return service.get_project_threads(session_id)

@router.post("/threads", response_model=schemas.Thread)
def create_thread(thread: schemas.ThreadCreate, db: Session = Depends(get_db)):
    service = ChatService(db)
    return service.create_thread(thread)

@router.post("/threads/{thread_id}/messages", response_model=schemas.Message)
def post_message(thread_id: str, message: schemas.MessageCreate, db: Session = Depends(get_db)):
    service = ChatService(db)
    # Check if thread exists
    thread = db.query(models.Thread).filter(models.Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    db_msg = service.add_message(thread_id, message)
    return db_msg

@router.post("/threads/{thread_id}/messages/user", response_model=schemas.Message)
def post_user_message(thread_id: str, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """
    Simplified endpoint for posting user messages.
    Payload: {"content": "...", "meta": {...}}
    """
    content = payload.get("content")
    if not content:
        raise HTTPException(status_code=422, detail="Content is required")
    
    meta = payload.get("meta")
    
    msg_create = schemas.MessageCreate(role="user", content=content, meta=meta)
    return post_message(thread_id, msg_create, db)

class ReplyRequest(BaseModel):
    mode: str = "global" # global / breakout
    include_code: bool = True
    temperature: Optional[float] = 0.7

from backend.services.llm_stream import stream_and_persist_reply
import json

@router.post("/threads/{thread_id}/assistant_reply", response_model=schemas.Message)
async def generate_assistant_reply(
    thread_id: str, 
    req: ReplyRequest, 
    db: Session = Depends(get_db)
):
    # 1. Rate Limiting (10s per thread)
    now = time.time()
    last_req = _rate_limit_store.get(thread_id, 0)
    if now - last_req < 2: # Reduced for testing
        raise HTTPException(
            status_code=429, 
            detail={"code": "RATE_LIMIT", "message": "Please wait before sending another message."}
        )
    _rate_limit_store[thread_id] = now

    service = ChatService(db)
    
    # 2. Get Thread & Messages
    thread = db.query(models.Thread).filter(models.Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
        
    messages = service.get_thread_messages(thread_id)
    
    # 3. Get Context (Code Snapshot)
    extra_context = {}
    if req.include_code:
        # Get latest snapshot for the session
        snap = db.query(models.CodeSnapshot)\
            .filter(models.CodeSnapshot.session_id == thread.session_id)\
            .order_by(models.CodeSnapshot.created_at.desc())\
            .first()
        if snap:
            extra_context["code"] = snap.content
            
    if thread.type == "breakout" and thread.anchor:
        extra_context["breakout_anchor"] = thread.anchor

    # 4. Construct Prompt
    # Find last user message
    last_user_msg = next((m for m in reversed(messages) if m.role == "user"), None)
    base_prompt = last_user_msg.content if last_user_msg else "Hello"
    
    full_prompt = base_prompt
    if extra_context:
        full_prompt += f"\n\nContext:\n{json.dumps(extra_context, indent=2)}"

    # 5. Stream & Persist
    # We await this, so the API response waits for the stream to finish.
    # This ensures "ai_state: done" is sent before we return.
    msg_id = await stream_and_persist_reply(thread.session_id, thread_id, full_prompt, db, req.mode)
    
    # 6. Return Created Message
    created_msg = db.query(models.Message).filter(models.Message.id == msg_id).first()
    return created_msg

@router.get("/threads/{thread_id}/messages", response_model=List[schemas.Message])
def get_messages(thread_id: str, db: Session = Depends(get_db)):
    service = ChatService(db)
    return service.get_thread_messages(thread_id)

@router.get("/session/{session_id}/messages", response_model=List[schemas.Message])
def get_session_messages(session_id: str, thread_id: Optional[str] = None, db: Session = Depends(get_db)):
    service = ChatService(db)
    if thread_id:
        return service.get_thread_messages(thread_id)
    
    # If no thread_id, find general thread for session
    # Or return all messages (might be too many). 
    # For compliance with "GET /api/session/{id}/messages?thread_id=xxx", strict filtering is enough.
    # But if thread_id is missing, let's try to find general thread.
    thread = db.query(models.Thread)\
        .filter(models.Thread.session_id == session_id)\
        .filter(models.Thread.type == "global")\
        .first()
    if thread:
        return service.get_thread_messages(thread.id)
    return []

@router.post("/threads/{thread_id}/summary")
def generate_summary(thread_id: str, db: Session = Depends(get_db)):
    service = ChatService(db)
    messages = service.get_thread_messages(thread_id)
    if not messages:
        return {"summary": "No messages."}
    
    context = "\n".join([f"{m.role}: {m.content}" for m in messages[-10:]])
    prompt = f"Summarize this conversation briefly:\n{context}"
    summary = llm_service.generate_hint(prompt)
    
    thread = db.query(models.Thread).filter(models.Thread.id == thread_id).first()
    if thread:
        thread.summary = summary
        db.commit()
        
    return {"summary": summary}


@router.patch("/threads/{thread_id}", response_model=schemas.Thread)
def update_thread(thread_id: str, patch: schemas.ThreadUpdate, db: Session = Depends(get_db)):
    thread = db.query(models.Thread).filter(models.Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if patch.title is not None:
        thread.title = patch.title
    if patch.summary is not None:
        thread.summary = patch.summary
    if patch.collapsed is not None:
        thread.collapsed = patch.collapsed

    db.commit()
    db.refresh(thread)
    return thread

# Unified Breakout creation via threads endpoint or specific one
@router.post("/sessions/{session_id}/threads/breakout", response_model=schemas.Thread)
def create_breakout(session_id: str, breakout: schemas.ThreadCreate, db: Session = Depends(get_db)):
    # Enforce type="breakout" and session_id
    breakout.session_id = session_id
    breakout.type = "breakout"
    service = ChatService(db)
    return service.create_thread(breakout)

class BreakoutRequest(BaseModel):
    range: Dict[str, int]
    title: Optional[str] = "Breakout"

@router.post("/session/{session_id}/breakout", response_model=schemas.Thread)
def create_breakout_alias(session_id: str, req: BreakoutRequest, db: Session = Depends(get_db)):
    """Alias for /sessions/{session_id}/threads/breakout with 2.7-F payload"""
    # Map range to anchor
    anchor = {
        "line_start": req.range.get("start_line", req.range.get("start", 0)),
        "line_end": req.range.get("end_line", req.range.get("end", 0)),
        "col_start": req.range.get("start_col", 0),
        "col_end": req.range.get("end_col", 0)
    }
    
    thread_create = schemas.ThreadCreate(
        session_id=session_id,
        type="breakout",
        title=req.title or "Breakout",
        anchor=anchor
    )
    service = ChatService(db)
    return service.create_thread(thread_create)

class Marker(BaseModel):
    thread_id: str
    line: int
    title: Optional[str]

@router.get("/markers", response_model=List[Marker])
def get_markers(session_id: str, file_id: Optional[str] = None, db: Session = Depends(get_db)):
    # ... (existing implementation) ...
    # Find breakout threads for this session
    query = db.query(models.Thread).filter(
        models.Thread.session_id == session_id,
        models.Thread.type == "breakout"
    )
    threads = query.all()
    
    markers = []
    for t in threads:
        # Check if anchor matches file_id (if provided)
        anchor = t.anchor or {}
        # If file_id is provided, check if anchor has it
        if file_id and anchor.get("file") != file_id:
            continue
            
        if "line_start" in anchor:
            markers.append(Marker(
                thread_id=t.id,
                line=anchor["line_start"],
                title=t.title
            ))
    return markers

# --- Breakout API (4.1.2) ---
@router.post("/breakouts", response_model=schemas.Thread)
def create_breakout_global(req: BreakoutRequest, session_id: str, db: Session = Depends(get_db)):
    """Global alias for creating breakout"""
    return create_breakout_alias(session_id, req, db)

@router.get("/breakouts/{breakout_id}", response_model=schemas.Thread)
def get_breakout(breakout_id: str, db: Session = Depends(get_db)):
    thread = db.query(models.Thread).filter(models.Thread.id == breakout_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Breakout not found")
    return thread

@router.post("/breakouts/{breakout_id}/summary")
def generate_breakout_summary(breakout_id: str, db: Session = Depends(get_db)):
    return generate_summary(breakout_id, db)
