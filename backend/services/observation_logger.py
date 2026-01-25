import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


MAX_TEXT_BYTES = 8 * 1024


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_text(s: Optional[str], max_bytes: int = MAX_TEXT_BYTES) -> Optional[str]:
    if s is None:
        return None
    b = s.encode("utf-8", errors="replace")
    if len(b) <= max_bytes:
        return s
    truncated = b[:max_bytes].decode("utf-8", errors="replace")
    return truncated


_SECRET_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"(sk-[A-Za-z0-9]{10,})"),
    re.compile(r"(OPENAI_API_KEY\s*=\s*['\"][^'\"]+['\"])"),
    re.compile(r"(Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*)", re.IGNORECASE),
)


def _scrub_secrets(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    out = s
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def _extract_error(stderr: Optional[str]) -> Dict[str, Any]:
    if not stderr:
        return {"error_type": None, "error_message": None, "stack_trace": None, "error_file": None, "error_line": None}

    s = stderr
    py_type = None
    py_msg = None
    py_line = None
    py_file = None

    m_type = re.search(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*Error|Exception)\s*:\s*(.*)\s*$", s)
    if m_type:
        py_type = m_type.group(1)
        py_msg = m_type.group(2).strip() if m_type.group(2) else ""

    m_file = re.findall(r'(?m)^\s*File\s+"([^"]+)",\s+line\s+(\d+)', s)
    if m_file:
        py_file, py_line_s = m_file[-1]
        try:
            py_line = int(py_line_s)
        except Exception:
            py_line = None

    js_type = None
    js_msg = None
    js_file = None
    js_line = None
    m_js = re.search(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*Error)\s*:\s*(.*)\s*$", s)
    if m_js and not py_type:
        js_type = m_js.group(1)
        js_msg = m_js.group(2).strip() if m_js.group(2) else ""
        m_at = re.search(r"(?m)\bat\s+.*\((.*):(\d+):(\d+)\)", s)
        if m_at:
            js_file = m_at.group(1)
            try:
                js_line = int(m_at.group(2))
            except Exception:
                js_line = None

    err_type = py_type or js_type
    err_msg = py_msg or js_msg
    err_file = py_file or js_file
    err_line = py_line if py_line is not None else js_line

    return {
        "error_type": err_type,
        "error_message": err_msg,
        "stack_trace": _truncate_text(_scrub_secrets(s)),
        "error_file": err_file,
        "error_line": err_line,
    }


@dataclass
class ObservationEventContext:
    session_id: str
    event_id: str
    event_type: str
    source: str
    trace_id: Optional[str] = None
    code_state_id: Optional[str] = None


class ObservationLogger:
    def __init__(self, repo_root: Optional[Path] = None):
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._seq_cache: Dict[str, int] = {}
        self._started: set[str] = set()

    def _log_path(self, session_id: str) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._repo_root / "logs" / "observations" / day / f"{session_id}.jsonl"

    def _ensure_dir(self, path: Path) -> None:
        os.makedirs(path.parent, exist_ok=True)

    def _load_last_seq(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            with path.open("rb") as f:
                data = f.read()
            if not data:
                return 0
            lines = data.splitlines()
            for raw in reversed(lines[-50:]):
                try:
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
                except Exception:
                    continue
                seq = obj.get("seq")
                if isinstance(seq, int) and seq >= 0:
                    return seq + 1
        except Exception:
            return 0
        return 0

    def _next_seq(self, session_id: str, path: Path) -> int:
        if session_id not in self._seq_cache:
            self._seq_cache[session_id] = self._load_last_seq(path)
        seq = self._seq_cache[session_id]
        self._seq_cache[session_id] = seq + 1
        return seq

    def append(self, ctx: ObservationEventContext, payload: Dict[str, Any]) -> Path:
        path = self._log_path(ctx.session_id)
        self._ensure_dir(path)
        seq = self._next_seq(ctx.session_id, path)

        evt_type = ctx.event_type
        mapped_type = evt_type
        if evt_type == "run":
            mapped_type = "run_start"
        elif evt_type in ("run_ok", "run_fail"):
            mapped_type = "run_end"
        elif evt_type == "test":
            mapped_type = "test_start"
        elif evt_type in ("test_pass", "test_fail"):
            mapped_type = "test_end"

        out_payload: Dict[str, Any] = dict(payload or {})

        if mapped_type in ("run_end", "test_end"):
            out_payload["stdout_snippet"] = _truncate_text(_scrub_secrets(out_payload.get("stdout_snippet") or out_payload.get("stdout")))
            out_payload["stderr_snippet"] = _truncate_text(_scrub_secrets(out_payload.get("stderr_snippet") or out_payload.get("stderr")))
            err = _extract_error(out_payload.get("stderr_snippet"))
            out_payload.update(err)

        record = {
            "schema_version": "1.0",
            "event_id": ctx.event_id,
            "timestamp": _iso_now(),
            "session_id": ctx.session_id,
            "task_id": out_payload.get("task_id"),
            "task_text": out_payload.get("task_text"),
            "event_type": mapped_type,
            "source": ctx.source,
            "seq": seq,
            "trace_id": ctx.trace_id,
            "code_state_id": ctx.code_state_id,
            "payload": out_payload,
        }

        line = json.dumps(record, ensure_ascii=False)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
        return path

    def ensure_session_started(
        self,
        session_id: str,
        *,
        language: str = "python",
        task_id: Optional[str] = None,
        task_text: Optional[str] = None,
        run_command: Optional[str] = None,
        has_tests: Optional[bool] = None,
    ) -> Path:
        if session_id in self._started:
            return self._log_path(session_id)

        path = self._log_path(session_id)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8", errors="replace") as f:
                    for _ in range(20):
                        line = f.readline()
                        if not line:
                            break
                        obj = json.loads(line)
                        if obj.get("event_type") == "session_start":
                            self._started.add(session_id)
                            return path
            except Exception:
                pass

        ctx = ObservationEventContext(
            session_id=session_id,
            event_id=f"session_start_{int(time.time() * 1000)}",
            event_type="session_start",
            source="backend",
        )
        payload = {
            "task_id": task_id,
            "task_text": task_text,
            "language": language,
            "run_command": run_command,
            "has_tests": has_tests,
        }
        out_path = self.append(ctx, payload)
        self._started.add(session_id)
        return out_path

    def end_session(self, session_id: str, *, reason: Optional[str] = None, event_count: Optional[int] = None) -> Path:
        ctx = ObservationEventContext(
            session_id=session_id,
            event_id=f"session_end_{int(time.time() * 1000)}",
            event_type="session_end",
            source="backend",
        )
        payload: Dict[str, Any] = {"reason": reason, "event_count": event_count}
        return self.append(ctx, payload)


observation_logger = ObservationLogger()
