from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas, utils
from backend.services.policy import decide_action
from backend.services.llm_service import llm_service
from backend.services.prompting import build_intervention_prompt
from backend.services.chat_service import ChatService
from backend.services.websocket_service import manager
from backend.services.telemetry import telemetry_service
from backend.services.diagnosis_pipeline import DiagnosisPipeline
from backend.services.observation_logger import observation_logger, ObservationEventContext
from typing import List, Dict, Any
import logging
import hashlib
import traceback

logger = logging.getLogger("Backend")
router = APIRouter()

# --- Code State API (3.1-C) ---
@router.post("/code_states", response_model=Dict[str, str])
async def create_code_state(data: schemas.CodeStateCreate, db: Session = Depends(get_db)):
    # Calculate Hash
    content_hash = hashlib.md5(data.content.encode("utf-8")).hexdigest()
    
    # Check existence (deduplication) - optional, but good for storage
    existing = db.query(models.CodeState).filter(
        models.CodeState.session_id == data.session_id, 
        models.CodeState.content_hash == content_hash
    ).first()
    
    if existing:
        return {"code_state_id": existing.id, "content_hash": existing.content_hash}
        
    # Create New
    new_state = models.CodeState(
        id=utils.uid("cs"),
        session_id=data.session_id,
        content=data.content,
        content_hash=content_hash,
        trace_id=data.trace_id
    )
    db.add(new_state)
    db.commit()
    db.refresh(new_state)
    
    return {"code_state_id": new_state.id, "content_hash": new_state.content_hash}

# --- Events API ---

@router.post("/sessions/{session_id}/events", response_model=schemas.EventLog)
async def create_event(session_id: str, event: schemas.EventLogCreate, db: Session = Depends(get_db)):
    # 1. Save Event
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
        
    db_event = models.EventLog(
        id=utils.uid("evt"),
        session_id=session_id,
        type=event.type,
        payload=event.payload,
        trace_id=event.trace_id,
        code_state_id=event.code_state_id
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    try:
        observation_logger.ensure_session_started(
            session_id,
            language=sess.language if sess else "python",
            task_id=(event.payload or {}).get("task_id"),
            task_text=(event.payload or {}).get("task_text"),
            run_command=(event.payload or {}).get("run_command"),
            has_tests=(event.payload or {}).get("has_tests"),
        )
        observation_logger.append(
            ObservationEventContext(
                session_id=session_id,
                event_id=db_event.id,
                event_type=db_event.type,
                source="frontend",
                trace_id=db_event.trace_id,
                code_state_id=db_event.code_state_id,
            ),
            event.payload or {},
        )
    except Exception:
        logger.exception("ObservationLogger append failed")
    
    # 2. Track Telemetry (3.2-A/B)
    telemetry_service.track_event(session_id, event.type, event.payload)
    
    # 3. Check for Mechanism Trigger
    trigger_types = ["compile", "compile_error", "run", "test", "idle", "test_pass", "unlock_attempt", "recap_response"]
    if event.type in trigger_types:
        try:
            await run_mechanism_pipeline(session_id, db_event, db)
        except Exception as e:
            logger.error(f"Mechanism failed: {e}")
            traceback.print_exc()
            # Do not fail the event logging itself
            
    return db_event

@router.post("/session/{session_id}/event", response_model=schemas.EventLog)
async def create_event_alias(session_id: str, event: schemas.EventLogCreate, db: Session = Depends(get_db)):
    """Alias for /sessions/{session_id}/events to match 1234.md spec"""
    return await create_event(session_id, event, db)

@router.get("/sessions/{session_id}/events", response_model=List[schemas.EventLog])
def get_events(session_id: str, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.EventLog)\
        .filter(models.EventLog.session_id == session_id)\
        .order_by(models.EventLog.created_at.desc())\
        .limit(limit)\
        .all()

# --- Mechanism Pipeline ---
async def run_mechanism_pipeline(session_id: str, event: models.EventLog, db: Session):
    trace_id = event.trace_id

    pipeline = DiagnosisPipeline(db)
    try:
        diagnosis = await pipeline.run_diagnosis(session_id, event.id)
    except Exception as e:
        logger.error(f"DiagnosisPipeline failed: {e}")
        traceback.print_exc()
        return

    diag = diagnosis.model_dump() if hasattr(diagnosis, "model_dump") else dict(diagnosis)

    raw_code = ""
    if event.code_state_id:
        cs = db.query(models.CodeState).filter(models.CodeState.id == event.code_state_id).first()
        if cs:
            raw_code = cs.content or ""

    if not raw_code:
        snap = db.query(models.CodeSnapshot)\
            .filter(models.CodeSnapshot.session_id == session_id)\
            .order_by(models.CodeSnapshot.created_at.desc())\
            .first()
        if snap:
            raw_code = snap.content or ""

    plan = decide_action(
        event=event,
        diagnose_result=diag,
        session_id=session_id,
        context={"code": raw_code, "problem_id": (event.payload or {}).get("problem_id")}
    )

    highlights = plan.ui_actions.get("highlight_spans", [])
    if highlights:
        await manager.broadcast(session_id, {
            "type": "highlight_spans",
            "spans": highlights,
            "ttl_ms": 5000,
            "trace_id": trace_id
        })

    await manager.broadcast(session_id, {
        "type": "intervention_plan",
        "data": {
            "leaf_level": plan.leaf_level,
            "fading_direction": plan.fading_direction,
            "unlock_required": plan.unlock_required,
            "unlock_question": plan.unlock_question,
            "is_debt_recap": plan.is_debt_recap
        },
        "trace_id": trace_id
    })

    if not plan.interrupt:
        return

    chat_service = ChatService(db)
    target_tid = (event.payload or {}).get("breakout_thread_id")
    if not target_tid:
        general = db.query(models.Thread)\
            .filter(models.Thread.session_id == session_id)\
            .filter(models.Thread.type == "global")\
            .first()
        target_tid = general.id if general else None

    if not target_tid:
        return

    await manager.broadcast(session_id, {
        "type": "ai_state",
        "state": "thinking",
        "thread_id": target_tid,
        "scope": "global",
        "trace_id": trace_id
    })

    full_content = ""
    message_id = utils.uid("msg")

    if plan.need_llm:
        prompt_msgs = build_intervention_prompt(
            diagnose_result=diag,
            code_excerpt=raw_code[-500:] if raw_code else "",
            event=event,
            ceiling=plan.ceiling,
            mode=plan.llm_mode or "logic_help"
        )

        await manager.broadcast(session_id, {
            "type": "assistant_message_begin",
            "thread_id": target_tid,
            "message_id": message_id,
            "trace_id": trace_id
        })

        await manager.broadcast(session_id, {
            "type": "ai_state",
            "state": "writing",
            "thread_id": target_tid,
            "trace_id": trace_id
        })

        try:
            stream_gen = llm_service.stream_completion(prompt_msgs, model="gpt-4o-mini")
            seq = 0
            for chunk in stream_gen:
                await manager.broadcast(session_id, {
                    "type": "ai_text_chunk",
                    "thread_id": target_tid,
                    "message_id": message_id,
                    "delta": chunk,
                    "seq": seq,
                    "is_final": False,
                    "trace_id": trace_id
                })
                seq += 1
                full_content += chunk
        except Exception as e:
            await manager.broadcast(session_id, {
                "type": "ai_state",
                "state": "error",
                "thread_id": target_tid,
                "meta": {"error": str(e)},
                "trace_id": trace_id
            })
            return
    else:
        full_content = plan.assistant_message or "Let's review your code."

        await manager.broadcast(session_id, {
            "type": "assistant_message_begin",
            "thread_id": target_tid,
            "message_id": message_id,
            "trace_id": trace_id
        })
        await manager.broadcast(session_id, {
            "type": "ai_state",
            "state": "writing",
            "thread_id": target_tid,
            "trace_id": trace_id
        })
        await manager.broadcast(session_id, {
            "type": "ai_text_chunk",
            "thread_id": target_tid,
            "message_id": message_id,
            "delta": full_content,
            "seq": 0,
            "is_final": False,
            "trace_id": trace_id
        })

    await manager.broadcast(session_id, {
        "type": "ai_text_chunk",
        "thread_id": target_tid,
        "message_id": message_id,
        "delta": "",
        "seq": 999999,
        "is_final": True,
        "trace_id": trace_id
    })
    await manager.broadcast(session_id, {
        "type": "ai_state",
        "state": "done",
        "thread_id": target_tid,
        "message_id": message_id,
        "trace_id": trace_id
    })

    meta = {
        "diagnosis": {
            "err_type_coarse": diag.get("err_type_coarse"),
            "err_type_pedagogical": diag.get("err_type_pedagogical"),
            "spans": (diag.get("evidence") or {}).get("spans") or [],
            "recommendations": diag.get("recommendations") or []
        },
        "policy_mode": plan.llm_mode,
        "leaf_state": {
            "level": plan.leaf_level,
            "fading": plan.fading_direction,
            "unlock": plan.unlock_required,
            "debt": plan.is_debt_recap
        },
        "streamed": True,
        "trace_id": trace_id
    }

    msg = schemas.MessageCreate(role="assistant", content=full_content, meta=meta)
    chat_service.add_message(target_tid, msg, message_id=message_id)

@router.post("/events", response_model=schemas.EventLog)
async def create_event_global_alias(event: schemas.EventLogCreate, db: Session = Depends(get_db)):
    """Global alias for /api/event if session_id is in payload, or fail"""
    # Payload must contain session_id if we use this global endpoint
    # But schema doesn't have session_id in top level.
    # We might need to extract it from payload or require it in query?
    # The requirement says "POST /api/event".
    # Let's assume the body contains session_id or we use a different schema.
    # For now, let's just make it compatible with the "session_id in path" by requiring it in query or body if possible.
    # Or just return an error saying "Use /sessions/{id}/events".
    # BUT, if I must implement it:
    if "session_id" in event.payload:
        return await create_event(event.payload["session_id"], event, db)
    raise HTTPException(status_code=400, detail="session_id required in payload for this endpoint")

@router.post("/event", response_model=schemas.EventLog)
async def create_event_singular_alias(event: schemas.EventLogCreate, db: Session = Depends(get_db)):
    """Alias for /api/event"""
    return await create_event_global_alias(event, db)
