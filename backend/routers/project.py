from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas, utils
from backend.services.chat_service import ChatService
from backend.services.observation_logger import observation_logger, ObservationEventContext
from typing import List

router = APIRouter()

# --- Workspace API ---
@router.post("/workspaces", response_model=schemas.Workspace)
def create_workspace(workspace: schemas.WorkspaceCreate, db: Session = Depends(get_db)):
    db_ws = models.Workspace(
        id=utils.uid("ws"),
        name=workspace.name
    )
    db.add(db_ws)
    db.commit()
    db.refresh(db_ws)
    return db_ws

@router.get("/workspaces", response_model=List[schemas.Workspace])
def get_workspaces(db: Session = Depends(get_db)):
    return db.query(models.Workspace).all()

@router.get("/session/default")
def get_default_session(db: Session = Depends(get_db)):
    # 1. Check if any session exists
    session = db.query(models.Session).first()
    
    if not session:
        # Create default workspace if needed
        workspace = db.query(models.Workspace).first()
        if not workspace:
            workspace = models.Workspace(id=utils.uid("ws"), name="Default Workspace")
            db.add(workspace)
            db.commit()
            db.refresh(workspace)
            
        # Create default session
        session = models.Session(
            id=utils.uid("sess"),
            workspace_id=workspace.id,
            title="Default Session",
            language="python"
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        
        # Seed General thread
        chat_service = ChatService(db)
        chat_service.create_thread(schemas.ThreadCreate(
            session_id=session.id,
            type="global",
            title="General",
            summary="Global discussion"
        ))
    
    # Get general thread id
    general_thread = db.query(models.Thread)\
        .filter(models.Thread.session_id == session.id)\
        .filter(models.Thread.type == "global")\
        .first()

    try:
        observation_logger.ensure_session_started(
            session.id,
            language=session.language,
            run_command="ui.run_or_test",
            has_tests=True,
        )
    except Exception:
        pass
        
    return {
        "session_id": session.id,
        "general_thread_id": general_thread.id if general_thread else None
    }

# --- Session API ---
@router.post("/sessions", response_model=schemas.Session)
def create_session(session: schemas.SessionCreate, db: Session = Depends(get_db)):
    # Verify workspace exists
    ws = db.query(models.Workspace).filter(models.Workspace.id == session.workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    db_session = models.Session(
        id=utils.uid("sess"),
        workspace_id=session.workspace_id,
        title=session.title,
        language=session.language
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    
    # Auto-seed General thread
    chat_service = ChatService(db)
    chat_service.create_thread(schemas.ThreadCreate(
        session_id=db_session.id,
        type="global",
        title="General",
        summary="Global discussion"
    ))

    try:
        observation_logger.ensure_session_started(
            db_session.id,
            language=db_session.language,
            run_command="ui.run_or_test",
            has_tests=True,
        )
    except Exception:
        pass
    
    return db_session

@router.get("/sessions/{session_id}", response_model=schemas.Session)
def get_session(session_id: str, db: Session = Depends(get_db)):
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess

@router.get("/sessions/{session_id}/threads", response_model=List[schemas.Thread])
def get_session_threads(session_id: str, db: Session = Depends(get_db)):
    return db.query(models.Thread).filter(models.Thread.session_id == session_id).all()

# --- CodeSnapshot API ---
@router.post("/sessions/{session_id}/code", response_model=schemas.CodeSnapshot)
def save_code_snapshot(session_id: str, snapshot: schemas.CodeSnapshotCreate, db: Session = Depends(get_db)):
    # Verify session
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
        
    db_snap = models.CodeSnapshot(
        id=utils.uid("snap"),
        session_id=session_id,
        content=snapshot.content,
        cursor_line=snapshot.cursor_line,
        cursor_col=snapshot.cursor_col
    )
    db.add(db_snap)
    
    # Update session updated_at
    sess.updated_at = utils.now()
    
    db.commit()
    db.refresh(db_snap)

    try:
        file_content = snapshot.content
        truncated = False
        if file_content and len(file_content.encode("utf-8", errors="replace")) > 200_000:
            file_content = file_content[:200_000]
            truncated = True

        observation_logger.append(
            ObservationEventContext(
                session_id=session_id,
                event_id=db_snap.id,
                event_type="snapshot",
                source="frontend",
            ),
            {
                "file_content": file_content,
                "cursor_line": snapshot.cursor_line,
                "cursor_col": snapshot.cursor_col,
                "selection_range": snapshot.selection_range,
                "visible_range": snapshot.visible_range,
                "file_path": snapshot.file_path or "main.py",
                "truncated": truncated,
            },
        )
    except Exception:
        pass
    return db_snap

@router.post("/session/{session_id}/snapshot", response_model=schemas.CodeSnapshot)
def save_code_snapshot_alias(session_id: str, snapshot: schemas.CodeSnapshotCreate, db: Session = Depends(get_db)):
    """Alias for /sessions/{session_id}/code to match 1234.md spec"""
    return save_code_snapshot(session_id, snapshot, db)


@router.post("/sessions/{session_id}/end")
def end_session(session_id: str, payload: schemas.SessionEndRequest, db: Session = Depends(get_db)):
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    event_count = db.query(models.EventLog).filter(models.EventLog.session_id == session_id).count()
    log_path = observation_logger.end_session(session_id, reason=payload.reason, event_count=event_count)
    return {"ok": True, "session_id": session_id, "event_count": event_count, "log_path": str(log_path)}

@router.get("/sessions/{session_id}/code/latest", response_model=schemas.CodeSnapshot)
def get_latest_code(session_id: str, db: Session = Depends(get_db)):
    snap = db.query(models.CodeSnapshot)\
        .filter(models.CodeSnapshot.session_id == session_id)\
        .order_by(models.CodeSnapshot.created_at.desc())\
        .first()
        
    if not snap:
        raise HTTPException(status_code=404, detail="No code snapshots found for this session")
    return snap

# --- Replay API ---
@router.get("/session/{session_id}/replay")
def replay_session(session_id: str, db: Session = Depends(get_db)):
    """Aggregate all session data for frontend restoration"""
    # 1. Session Info
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # 2. Threads (including breakouts)
    threads = db.query(models.Thread).filter(models.Thread.session_id == session_id).all()
    
    # 3. Markers (from table or derived from threads)
    # Using the separate Markers table if populated, or fallback to Thread anchors
    # For Part 2.8 compliance, we should use the Markers table if we start populating it,
    # but currently Breakouts are Threads with anchors. 
    # Let's return both or align. 
    # If we strictly follow B1 table list, we have a 'markers' table.
    # Let's query it.
    markers = db.query(models.Marker).filter(models.Marker.session_id == session_id).all()
    
    # 4. Latest Snapshot
    snap = db.query(models.CodeSnapshot)\
        .filter(models.CodeSnapshot.session_id == session_id)\
        .order_by(models.CodeSnapshot.created_at.desc())\
        .first()
        
    # 5. Messages (Flat list or grouped? Frontend usually fetches by thread. 
    # But replay might want initial set. Let's return all messages for simplicity or empty if lazy load)
    # To reduce payload, maybe just recent ones? 
    # Requirement D1 says "messages (grouped or flat)". Let's return flat.
    messages = db.query(models.Message)\
        .join(models.Thread)\
        .filter(models.Thread.session_id == session_id)\
        .all()
        
    return {
        "session": sess,
        "threads": threads,
        "markers": markers,
        "latest_snapshot": snap,
        "messages": messages
    }

# --- Deprecated / Migration Compatibility ---
# Keeping old endpoints if needed for transition, but directing to new logic where possible
