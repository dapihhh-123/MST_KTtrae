from typing import Any, Dict, List

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.services.psw_telemetry_logger import psw_telemetry_logger, TelemetryBatch


router = APIRouter(prefix="/telemetry", tags=["psw-telemetry"])


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    ts: int
    type: str
    payload: Dict[str, Any]


class TelemetryBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    events: List[TelemetryEvent] = Field(default_factory=list)


@router.post("/batch")
def append_batch(body: TelemetryBatchRequest, x_session_id: str | None = Header(default=None)) -> Dict[str, Any]:
    session_id = body.session_id or x_session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id_required")
    batch = TelemetryBatch(session_id=session_id, events=[e.model_dump() for e in body.events])
    path = psw_telemetry_logger.append_batch(batch)
    return {"ok": True, "path": str(path), "count": len(body.events)}


@router.get("/{session_id}/download")
def download(session_id: str) -> Response:
    content = psw_telemetry_logger.read(session_id)
    return Response(content=content, media_type="application/x-ndjson")
