from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# --- Shared Base ---
class BaseSchema(BaseModel):
    class Config:
        from_attributes = True

# --- Workspace ---
class WorkspaceCreate(BaseModel):
    name: str = "Default"

class Workspace(BaseSchema):
    id: str
    name: str
    created_at: float

# --- Session ---
class SessionCreate(BaseModel):
    workspace_id: str
    title: Optional[str] = "Untitled Session"
    language: Optional[str] = "python"

class Session(BaseSchema):
    id: str
    workspace_id: str
    title: str
    language: str
    created_at: float
    updated_at: float

# --- CodeSnapshot (Legacy/Simple) ---
class CodeSnapshotCreate(BaseModel):
    content: str
    cursor_line: Optional[int] = None
    cursor_col: Optional[int] = None
    file_path: Optional[str] = None
    selection_range: Optional[Dict[str, int]] = None
    visible_range: Optional[Dict[str, int]] = None

class CodeSnapshot(BaseSchema):
    id: str
    session_id: str
    content: str
    cursor_line: Optional[int]
    cursor_col: Optional[int]
    created_at: float


class SessionEndRequest(BaseModel):
    reason: Optional[str] = None

class CodeStateCreate(BaseModel):
    session_id: str
    content: str
    trace_id: Optional[str] = None

class CodeState(BaseSchema):
    id: str
    session_id: str
    content: str
    content_hash: str
    trace_id: Optional[str]
    created_at: float

# --- Thread ---
class ThreadCreate(BaseModel):
    session_id: Optional[str] = None # Optional for input, required in DB. Router/Service should handle it.
    type: str = "topic" # global/topic/breakout
    title: str = "General"
    summary: Optional[str] = None
    anchor: Optional[Dict[str, Any]] = None # {file, line_start, line_end}

class Thread(BaseSchema):
    id: str
    session_id: str
    type: str
    title: str
    summary: Optional[str]
    anchor: Optional[Dict[str, Any]]
    collapsed: bool
    created_at: float
    updated_at: float


class ThreadUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    collapsed: Optional[bool] = None

# --- Message ---
class MessageCreate(BaseModel):
    role: str
    content: str
    meta: Optional[Dict[str, Any]] = None

class Message(BaseSchema):
    id: str
    thread_id: str
    role: str
    content: str
    meta: Optional[Dict[str, Any]]
    created_at: float

# --- EventLog ---
class EventLogCreate(BaseModel):
    type: str
    payload: Dict[str, Any]
    trace_id: Optional[str] = None
    code_state_id: Optional[str] = None

class EventLog(BaseSchema):
    id: str
    session_id: str
    type: str
    payload: Dict[str, Any]
    trace_id: Optional[str] = None
    code_state_id: Optional[str] = None
    created_at: float

# --- AIRun ---
class AIRun(BaseSchema):
    id: str
    session_id: str
    thread_id: Optional[str]
    kind: str
    status: str
    created_at: float
    finished_at: Optional[float]
    meta: Optional[Dict[str, Any]]

# --- AIStreamChunk ---
class AIStreamChunk(BaseSchema):
    id: str
    run_id: str
    seq: int
    delta: str
    is_final: bool
    created_at: float

# --- EditorOp ---
class EditorOp(BaseSchema):
    id: str
    run_id: str
    op: Dict[str, Any]
    created_at: float

# --- Marker ---
class Marker(BaseSchema):
    id: str
    session_id: str
    thread_id: str
    range: Dict[str, Any]
    created_at: float


class CodeRunRequest(BaseModel):
    code: str
    timeout_sec: Optional[float] = 2.5


class CodeRunResponse(BaseModel):
    ok: bool
    mode: str
    exit_code: Optional[int] = None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool

# --- New Diagnosis Schemas (3.3) ---

class DiagnosisSpan(BaseModel):
    file: str
    start_line: int
    end_line: int
    kind: str # attention | diagnostic | provenance
    score: Optional[float] = None

class DiagnosisEvidence(BaseModel):
    spans: List[DiagnosisSpan]
    error_summary: str
    error_hash: Optional[str] = None # Normalized hash
    tests_summary: Optional[str] = None
    diff_summary: Optional[Dict[str, Any]] = None
    natural_language: str

class DiagnosisResult(BaseModel):
    session_id: str
    event_id: str
    thread_id: Optional[str] = None
    trace_id: Optional[str] = None
    err_type_coarse: str # CORRECT|COMPILE|LOGIC|UNKNOWN
    err_type_pedagogical: str # RECALL|ADJUSTMENT|MODIFICATION|DECOMPOSITION|UNKNOWN
    confidence: float
    evidence: DiagnosisEvidence
    recommendations: List[str]
    suggested_ceiling: Optional[int] = None
    suggested_leaf_start_level: Optional[str] = None
    debug: Optional[Dict[str, Any]] = None
