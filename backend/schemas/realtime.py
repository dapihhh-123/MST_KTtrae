from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

# 1. AI State
class AIStateMessage(BaseModel):
    type: str = "ai_state"
    state: str # "thinking" | "writing" | "done" | "error"
    scope: str = "global" # "global" | "breakout"
    thread_id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

# 2. AI Text Chunk (Streaming Text)
class AITextChunkMessage(BaseModel):
    type: str = "ai_text_chunk"
    thread_id: str
    message_id: str
    delta: str
    seq: int
    is_final: bool = False

# 3. AI Code Chunk (Streaming Code)
class TargetLoc(BaseModel):
    file: Optional[str] = None
    start_line: Optional[int] = None
    start_col: Optional[int] = None

class AICodeChunkMessage(BaseModel):
    type: str = "ai_code_chunk"
    target: TargetLoc
    delta: str
    is_final: bool = False

# 4. Editor Ops (Structured Patch)
class EditorOp(BaseModel):
    op: str # "replace" | "insert" | "delete"
    range: Dict[str, Any] # {start_line, start_col, end_line, end_col}
    text: Optional[str] = None

class EditorOpsMessage(BaseModel):
    type: str = "editor_ops"
    ops: List[EditorOp]

# 5. Highlight Spans (ShadowCursor)
class HighlightSpan(BaseModel):
    line_start: int
    line_end: int
    score: Optional[float] = 1.0

class HighlightSpansMessage(BaseModel):
    type: str = "highlight_spans"
    spans: List[HighlightSpan]
    ttl_ms: int = 5000

# 6. Breakout / Marker
class MarkerUpdateMessage(BaseModel):
    type: str = "marker_update"
    markers: List[Dict[str, Any]]

class BreakoutCreatedMessage(BaseModel):
    type: str = "breakout_created"
    thread_id: str
    marker_id: Optional[str] = None
    anchor: Optional[Dict[str, Any]] = None

# Union for validation if needed
RealtimeMessage = Union[
    AIStateMessage, 
    AITextChunkMessage, 
    AICodeChunkMessage, 
    EditorOpsMessage, 
    HighlightSpansMessage, 
    MarkerUpdateMessage, 
    BreakoutCreatedMessage
]
