import json
import time
from typing import Any, Dict, Optional

import requests


BASE_URL = "http://127.0.0.1:8000/api"


def post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def get(path: str) -> Dict[str, Any]:
    r = requests.get(f"{BASE_URL}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


def report_event(session_id: str, typ: str, payload: Dict[str, Any], trace_id: Optional[str] = None, code_state_id: Optional[str] = None):
    body: Dict[str, Any] = {"type": typ, "payload": payload}
    if trace_id:
        body["trace_id"] = trace_id
    if code_state_id:
        body["code_state_id"] = code_state_id
    post(f"/session/{session_id}/event", body)


def main():
    sess = get("/session/default")
    session_id = sess["session_id"]

    code_fail = "print(1/0)\n"
    code_ok = "print('ok')\n"

    trace1 = f"trace_{int(time.time()*1000)}"
    cs1 = post("/code_states", {"session_id": session_id, "content": code_fail, "trace_id": trace1})
    code_state_id1 = cs1["code_state_id"]

    report_event(session_id, "edit", {
        "event_subtype": "edit",
        "changed_range": {"startLine": 1, "startCol": 1, "endLine": 1, "endCol": 1},
        "lines_added": 1,
        "lines_deleted": 0
    })
    report_event(session_id, "edit", {
        "event_subtype": "paste",
        "changed_range": {"startLine": 1, "startCol": 1, "endLine": 1, "endCol": 1},
        "lines_added": 4,
        "lines_deleted": 0
    })
    report_event(session_id, "edit", {
        "event_subtype": "undo",
        "changed_range": {"startLine": 1, "startCol": 1, "endLine": 1, "endCol": 1},
        "lines_added": 0,
        "lines_deleted": 1
    })
    report_event(session_id, "edit", {"event_subtype": "save", "file_path": "main.py"})

    post(f"/session/{session_id}/snapshot", {
        "content": code_fail,
        "cursor_line": 1,
        "cursor_col": 1,
        "file_path": "main.py",
        "selection_range": {"start_line": 1, "start_col": 1, "end_line": 1, "end_col": 1}
    })

    report_event(session_id, "run", {"run_id": "run_1", "run_command": "python", "cwd": ".", "code_len": len(code_fail)}, trace_id=trace1, code_state_id=code_state_id1)
    res1 = post(f"/session/{session_id}/run", {"code": code_fail})
    report_event(session_id, "run_fail", {
        "success": res1.get("ok"),
        "exit_code": res1.get("exit_code"),
        "stdout_snippet": res1.get("stdout"),
        "stderr_snippet": res1.get("stderr"),
        "duration_ms": res1.get("duration_ms"),
        "timed_out": res1.get("timed_out")
    }, trace_id=trace1, code_state_id=code_state_id1)

    trace2 = f"trace_{int(time.time()*1000)+1}"
    cs2 = post("/code_states", {"session_id": session_id, "content": code_ok, "trace_id": trace2})
    code_state_id2 = cs2["code_state_id"]

    report_event(session_id, "edit", {
        "event_subtype": "edit",
        "changed_range": {"startLine": 1, "startCol": 1, "endLine": 1, "endCol": 1},
        "lines_added": 1,
        "lines_deleted": 1
    })

    post(f"/session/{session_id}/snapshot", {
        "content": code_ok,
        "cursor_line": 1,
        "cursor_col": 1,
        "file_path": "main.py",
        "selection_range": {"start_line": 1, "start_col": 1, "end_line": 1, "end_col": 1}
    })

    report_event(session_id, "run", {"run_id": "run_2", "run_command": "python", "cwd": ".", "code_len": len(code_ok)}, trace_id=trace2, code_state_id=code_state_id2)
    res2 = post(f"/session/{session_id}/run", {"code": code_ok})
    report_event(session_id, "run_ok", {
        "success": res2.get("ok"),
        "exit_code": res2.get("exit_code"),
        "stdout_snippet": res2.get("stdout"),
        "stderr_snippet": res2.get("stderr"),
        "duration_ms": res2.get("duration_ms"),
        "timed_out": res2.get("timed_out")
    }, trace_id=trace2, code_state_id=code_state_id2)

    end = post(f"/sessions/{session_id}/end", {"reason": "script_generated"})
    print(json.dumps({"session_id": session_id, "end": end}, indent=2))


if __name__ == "__main__":
    main()

