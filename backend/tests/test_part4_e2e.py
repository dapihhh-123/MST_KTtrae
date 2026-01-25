import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import json
from backend.main import app
from backend.services.llm_service import llm_service

client = TestClient(app)

# Mock LLM
mock_llm = MagicMock()
mock_llm.generate_hint.return_value = "Try checking the variable name."
mock_llm.stream_completion.side_effect = lambda *args, **kwargs: iter(["Try ", "checking ", "variable."])
llm_service.generate_hint = mock_llm.generate_hint
llm_service.stream_completion = mock_llm.stream_completion

def test_part4_e2e_flow():
    # 1. Create Session
    ws_res = client.post("/api/workspaces", json={"name": "TestWS"})
    ws_id = ws_res.json()["id"]
    
    sess_res = client.post("/api/sessions", json={"workspace_id": ws_id, "title": "TestSession"})
    session_id = sess_res.json()["id"]
    assert session_id is not None
    
    # 2. Post Code State
    client.post("/api/code_states", json={
        "session_id": session_id,
        "content": "print(undefined_var)",
        "trace_id": "trace_test_1"
    })
    
    # 3. Post Event (Trigger Diagnosis)
    # Using the global alias created in 4.1.3
    evt_res = client.post("/api/event", json={
        "type": "compile_error",
        "payload": {
            "session_id": session_id, # Required for alias
            "message": "NameError",
            "problem_id": "1"
        },
        "trace_id": "trace_test_1"
    })
    assert evt_res.status_code == 200
    
    # 4. Diagnose API (4.2.1)
    # Using session-based diagnose
    diag_res = client.post(f"/api/sessions/{session_id}/diagnose?latest=true")
    assert diag_res.status_code == 200
    data = diag_res.json()
    assert data["err_type_coarse"] == "COMPILE"
    
    # 5. LLM Intervention (4.3.1)
    intervention_res = client.post("/api/llm/generate_intervention", json={
        "diagnose_result": data,
        "code_excerpt": "print(undefined_var)",
        "event_type": "compile_error"
    })
    assert intervention_res.status_code == 200
    assert "assistant_message" in intervention_res.json()
    assert intervention_res.json()["assistant_message"] == "Try checking the variable name."
    
    # 6. LLM Stream (4.3.2)
    stream_res = client.post("/api/ai/write/stream", json={"prompt": "Fix it"})
    assert stream_res.status_code == 200
    # StreamingResponse content
    content = b"".join(stream_res.iter_bytes())
    print(f"\n[DEBUG] Stream Content: {content}")
    assert content == b"Try checking variable."

    # 7. Breakout API (4.1.2)
    # Create
    br_res = client.post("/api/breakouts", json={
        "title": "Fix NameError",
        "range": {"start_line": 1, "end_line": 1}
    }, params={"session_id": session_id})
    assert br_res.status_code == 200
    br_id = br_res.json()["id"]
    
    # Get
    br_get = client.get(f"/api/breakouts/{br_id}")
    assert br_get.status_code == 200
    assert br_get.json()["id"] == br_id
    
    # Summary
    br_sum = client.post(f"/api/breakouts/{br_id}/summary")
    assert br_sum.status_code == 200
    
    print("\n[SUCCESS] Part 4 E2E Test Passed")

if __name__ == "__main__":
    test_part4_e2e_flow()
