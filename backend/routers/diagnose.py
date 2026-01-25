from fastapi import APIRouter, HTTPException, Depends
from backend import schemas, models
from backend.services.diagnosis_pipeline import DiagnosisPipeline
from backend.database import get_db
from sqlalchemy.orm import Session
import logging
from typing import List, Optional

logger = logging.getLogger("Backend")
router = APIRouter()

# --- New Endpoints for 3.3.6 ---

@router.post("/api/sessions/{session_id}/diagnose", response_model=schemas.DiagnosisResult)
async def run_session_diagnosis(
    session_id: str, 
    event_id: Optional[str] = None, 
    latest: bool = False,
    db: Session = Depends(get_db)
):
    """
    Trigger a full diagnosis (Coarse + Pedagogical) for a given event or latest event.
    """
    pipeline = DiagnosisPipeline(db)
    
    if latest:
        # Find latest diagnostic event (compile or test fail)
        last_event = db.query(models.EventLog)\
            .filter(models.EventLog.session_id == session_id)\
            .filter(models.EventLog.type.in_(["compile_error", "test_fail", "run_fail"]))\
            .order_by(models.EventLog.created_at.desc())\
            .first()
        if not last_event:
             raise HTTPException(status_code=404, detail="No diagnostic events found for this session")
        event_id = last_event.id
    
    if not event_id:
        raise HTTPException(status_code=400, detail="Must provide event_id or latest=true")
        
    result = await pipeline.run_diagnosis(session_id, event_id)
    return result

@router.get("/api/sessions/{session_id}/diagnoses", response_model=List[schemas.DiagnosisResult])
def get_session_diagnoses(session_id: str, limit: int = 5, db: Session = Depends(get_db)):
    """
    Get recent diagnosis logs for a session.
    """
    logs = db.query(models.DiagnosisLog)\
        .filter(models.DiagnosisLog.session_id == session_id)\
        .order_by(models.DiagnosisLog.created_at.desc())\
        .limit(limit)\
        .all()
    
    results = []
    for log in logs:
        # Pydantic doesn't automatically convert nested JSON columns if they are just Dicts
        # We need to ensure the evidence dict matches DiagnosisEvidence structure
        evidence_data = log.evidence_json or {}
        evidence = schemas.DiagnosisEvidence(**evidence_data)
        
        res = schemas.DiagnosisResult(
            session_id=log.session_id,
            event_id=log.event_id or "",
            thread_id=log.thread_id,
            err_type_coarse=log.err_type_coarse,
            err_type_pedagogical=log.err_type_pedagogical,
            confidence=log.confidence,
            evidence=evidence,
            recommendations=log.recommendations_json or [],
            debug=log.debug_json
        )
        results.append(res)
    return results
