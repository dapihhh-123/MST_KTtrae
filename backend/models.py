
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.database import Base
from backend.utils import uid, now

# 1) Workspace
class Workspace(Base):
    __tablename__ = "workspaces"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, default="Default")
    created_at = Column(Float, default=now)
    
    sessions = relationship("Session", back_populates="workspace")

# 2) Session (Replaces old 'Project' concept partially)
class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"))
    title = Column(String, default="Untitled Session")
    language = Column(String, default="python")
    created_at = Column(Float, default=now)
    updated_at = Column(Float, default=now)
    
    workspace = relationship("Workspace", back_populates="sessions")
    threads = relationship("Thread", back_populates="session")
    snapshots = relationship("CodeSnapshot", back_populates="session")
    events = relationship("EventLog", back_populates="session")

# 3) CodeSnapshot
class CodeSnapshot(Base):
    __tablename__ = "code_snapshots"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    content = Column(Text)
    cursor_line = Column(Integer, nullable=True)
    cursor_col = Column(Integer, nullable=True)
    created_at = Column(Float, default=now)
    
    session = relationship("Session", back_populates="snapshots")

# 4) Thread
class Thread(Base):
    __tablename__ = "threads"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    type = Column(String) # "global" | "topic" | "breakout"
    title = Column(String)
    anchor = Column(JSON, nullable=True) # {file, line_start, line_end}
    summary = Column(Text, nullable=True)
    collapsed = Column(Boolean, default=False)
    created_at = Column(Float, default=now)
    updated_at = Column(Float, default=now)
    
    session = relationship("Session", back_populates="threads")
    messages = relationship("Message", back_populates="thread")

# 5) Message
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, index=True)
    thread_id = Column(String, ForeignKey("threads.id"), index=True)
    role = Column(String) # "user" | "assistant" | "system"
    content = Column(Text)
    meta = Column(JSON, nullable=True)
    created_at = Column(Float, default=now)
    
    thread = relationship("Thread", back_populates="messages")

# 6) EventLog
class EventLog(Base):
    __tablename__ = "event_logs"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    type = Column(String) # "edit", "compile", "run", etc.
    payload = Column(JSON)
    trace_id = Column(String, nullable=True)
    code_state_id = Column(String, ForeignKey("code_states.id"), nullable=True)
    created_at = Column(Float, default=now)
    
    session = relationship("Session", back_populates="events")
    code_state = relationship("CodeState", back_populates="events")

# Fix: In original read output:
# code_state = relationship("CodeState", back_populates="events")
# And in CodeState: events = relationship("EventLog", back_populates="code_state")

# 6.1) CodeState (Immutable snapshot for causality)
class CodeState(Base):
    __tablename__ = "code_states"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    content = Column(Text)
    content_hash = Column(String, index=True)
    trace_id = Column(String, nullable=True)
    created_at = Column(Float, default=now)
    
    events = relationship("EventLog", back_populates="code_state")

# 7) AIRun
class AIRun(Base):
    __tablename__ = "ai_runs"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    thread_id = Column(String, ForeignKey("threads.id"), nullable=True)
    kind = Column(String) # "mechanism" | "ai_write"
    status = Column(String) # "thinking" | "writing" | "done" | "error"
    created_at = Column(Float, default=now)
    finished_at = Column(Float, nullable=True)
    meta = Column(JSON, nullable=True)
    
    stream_chunks = relationship("AIStreamChunk", back_populates="run")
    editor_ops = relationship("EditorOp", back_populates="run")

# 8) AIStreamChunk
class AIStreamChunk(Base):
    __tablename__ = "ai_stream_chunks"
    
    id = Column(String, primary_key=True, index=True)
    run_id = Column(String, ForeignKey("ai_runs.id"), index=True)
    seq = Column(Integer)
    delta = Column(Text)
    is_final = Column(Boolean, default=False)
    created_at = Column(Float, default=now)
    
    run = relationship("AIRun", back_populates="stream_chunks")

# 9) EditorOp
class EditorOp(Base):
    __tablename__ = "editor_ops"
    
    id = Column(String, primary_key=True, index=True)
    run_id = Column(String, ForeignKey("ai_runs.id"), index=True)
    op = Column(JSON) # {op, range, text}
    created_at = Column(Float, default=now)
    
    run = relationship("AIRun", back_populates="editor_ops")

# 10) Marker
class Marker(Base):
    __tablename__ = "markers"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    thread_id = Column(String, ForeignKey("threads.id"), index=True)
    range = Column(JSON) # {start_line, end_line, ...}
    created_at = Column(Float, default=now)

# 11) DiagnosisLog
class DiagnosisLog(Base):
    __tablename__ = "diagnosis_logs"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    event_id = Column(String, ForeignKey("event_logs.id"), nullable=True) # Optional link to trigger event
    thread_id = Column(String, nullable=True) # General or breakout
    trace_id = Column(String, nullable=True) # Inherited from event
    code_state_id = Column(String, nullable=True) # Inherited from event
    
    err_type_coarse = Column(String)
    err_type_pedagogical = Column(String)
    confidence = Column(Float)
    
    evidence_json = Column(JSON) # Stores DiagnosisEvidence
    recommendations_json = Column(JSON) # List[str]
    debug_json = Column(JSON, nullable=True)
    
    created_at = Column(Float, default=now)

# 12) LearningDebt
class LearningDebt(Base):
    __tablename__ = "learning_debts"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    concept_id = Column(String) # e.g., "rule_compile_recall"
    debt_level = Column(Integer, default=1)
    created_at = Column(Float, default=now)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(Float, nullable=True)

# 13) ConceptMastery
class ConceptMastery(Base):
    __tablename__ = "concept_mastery"
    
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    concept_id = Column(String) 
    mastery_score = Column(Float, default=0.0)
    last_updated_at = Column(Float, default=now)

# 14) OracleTask
class OracleTask(Base):
    __tablename__ = "oracle_tasks"
    
    task_id = Column(String, primary_key=True, index=True)
    project_id = Column(String, nullable=True)
    created_at = Column(Float, default=now)
    updated_at = Column(Float, default=now)

# 15) OracleTaskVersion
class OracleTaskVersion(Base):
    __tablename__ = "oracle_task_versions"
    
    version_id = Column(String, primary_key=True, index=True)
    task_id = Column(String, index=True) # Logical FK
    version_number = Column(Integer, default=1)
    status = Column(String) # ready, needs_clarification, etc.
    created_at = Column(Float, default=now)
    
    spec_json = Column(JSON)
    ambiguities_json = Column(JSON)
    user_confirmations_json = Column(JSON)
    
    public_examples_json = Column(JSON)
    hidden_tests_json = Column(JSON)
    
    oracle_confidence = Column(Float)
    conflict_report_json = Column(JSON)
    
    seed = Column(Integer)
    hash = Column(String)
    
    # Observability
    spec_llm_raw_json = Column(JSON, nullable=True)
    llm_raw_spec_json = Column(JSON, nullable=True) # Alias?
    spec_llm_request_id = Column(String, nullable=True)
    spec_prompt_version = Column(String, nullable=True)
    llm_model_used = Column(String, nullable=True)
    llm_provider_used = Column(String, nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    
    # Trace B1
    normalized_input_hash = Column(String, nullable=True)
    schema_version = Column(String, nullable=True)
    interaction_model_pred = Column(String, nullable=True)
    attempts = Column(Integer, nullable=True)
    attempt_fail_reasons_json = Column(JSON, nullable=True)
    missing_fields_json = Column(JSON, nullable=True)
    
    tests_llm_raw_json = Column(JSON, nullable=True)
    llm_raw_tests_json = Column(JSON, nullable=True)
    tests_llm_request_id = Column(String, nullable=True)
    tests_prompt_version = Column(String, nullable=True)

# 16) OracleRun
class OracleRun(Base):
    __tablename__ = "oracle_runs"
    
    run_id = Column(String, primary_key=True, index=True)
    version_id = Column(String, index=True)
    created_at = Column(Float, default=now)
    
    code_snapshot_id = Column(String, nullable=True)
    code_text = Column(Text, nullable=True)
    
    pass_rate = Column(Float)
    passed = Column(Integer)
    failed = Column(Integer)
    failures_summary_json = Column(JSON)
    
    runtime_ms = Column(Integer)
    memory_kb = Column(Integer)
    sandbox_mode = Column(String)
    resource_limits_json = Column(JSON)
    
    stdout_trunc = Column(Text, nullable=True)
    stderr_trunc = Column(Text, nullable=True)
    sandbox_exit_code = Column(Integer, nullable=True)
