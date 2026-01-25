from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import models, schemas
from backend.services.code_runner import run_python


router = APIRouter()


@router.post("/session/{session_id}/run", response_model=schemas.CodeRunResponse)
def run_code(session_id: str, req: schemas.CodeRunRequest, db: Session = Depends(get_db)):
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    result = run_python(req.code, mode="run", timeout_sec=req.timeout_sec or 2.5)
    return schemas.CodeRunResponse(
        ok=result.ok,
        mode="run",
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
    )


@router.post("/session/{session_id}/test", response_model=schemas.CodeRunResponse)
def test_code(session_id: str, req: schemas.CodeRunRequest, db: Session = Depends(get_db)):
    sess = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    result = run_python(req.code, mode="test", timeout_sec=req.timeout_sec or 2.5)
    return schemas.CodeRunResponse(
        ok=result.ok,
        mode="test",
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_ms=result.duration_ms,
        timed_out=result.timed_out,
    )

