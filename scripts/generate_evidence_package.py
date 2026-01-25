import sys
import os
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend import schemas, models
from backend.services.pedagogical_classifier import PedagogicalClassifier
from backend.services.diagnosis_pipeline import DiagnosisPipeline

# Mock DB Session
class MockDB:
    def __init__(self):
        self.items = []
        self.query_mock = MagicMock()
        self.filter_mock = MagicMock()
        
    def add(self, item):
        self.items.append(item)
        
    def commit(self):
        pass
        
    def query(self, model):
        self.query_mock.model = model
        return self
        
    def filter(self, *args):
        # Determine what to return based on the query model and args
        # This is a bit hacky but works for the specific pipeline calls
        if self.query_mock.model == models.Marker:
            # Mock a marker with a thread_id
            marker = MagicMock()
            marker.thread_id = "thread_breakout_123"
            self.first_return = marker
        elif self.query_mock.model == models.Thread:
            # Mock a global thread
            thread = MagicMock()
            thread.id = "thread_general_456"
            self.first_return = thread
        else:
            self.first_return = None
        return self
        
    def order_by(self, *args):
        return self
        
    def limit(self, *args):
        return self
        
    def first(self):
        return self.first_return
        
    def all(self):
        # Return what was added
        return [i for i in self.items if isinstance(i, models.DiagnosisLog)]

async def generate():
    print("=== 1. Compile Error DiagnosisResult ===")
    
    db = MockDB()
    pipeline = DiagnosisPipeline(db)
    
    # 1. Compile Error Run (RECALL)
    # Payload has marker_id, should resolve to breakout thread
    pipeline.context_builder.build = MagicMock(return_value={
        "session_id": "sess_1",
        "event_id": "evt_compile",
        "event_payload": {
            "message": "NameError: name 'unknown_var' is not defined",
            "marker_id": "marker_1" 
        },
        "current_code": "print(unknown_var)",
        "diff_summary": {"added_lines": 1, "removed_lines": 0, "total_changes": 1},
        "event": MagicMock(type="compile_error")
    })
    
    pipeline._get_coarse_diagnosis = MagicMock(return_value={
        "err_type_str": "COMPILE",
        "top_spans": [(1, 1)],
        "debug": {"logit": -2.0}
    })
    
    pipeline._notify_ws = AsyncMock()
    
    res_compile = await pipeline.run_diagnosis("sess_1", "evt_compile")
    print(json.dumps(res_compile.model_dump(), indent=2))
    print(f"\n[Verification] Thread ID resolved to: {res_compile.thread_id} (Expected: thread_breakout_123 from marker)")
    
    print("\n=== 2. Logic Error DiagnosisResult ===")
    
    # 2. Logic Error Run (MODIFICATION)
    # No thread info in payload, should default to General
    pipeline.context_builder.build = MagicMock(return_value={
        "session_id": "sess_1",
        "event_id": "evt_logic",
        "event_payload": {"tests_summary": "Test 'test_add' failed. Expected 3, got 4.", "stderr": ""},
        "current_code": "def add(a, b):\n    return a + b + 1",
        "diff_summary": {"added_lines": 1, "removed_lines": 1, "total_changes": 2},
        "event": MagicMock(type="test_fail")
    })
    
    pipeline._get_coarse_diagnosis = MagicMock(return_value={
        "err_type_str": "LOGIC",
        "top_spans": [(2, 2)],
        "debug": {"logit": 0.5}
    })
    
    # Reset DB mock for default thread query
    db.first_return = MagicMock(id="thread_general_456") 
    
    res_logic = await pipeline.run_diagnosis("sess_1", "evt_logic")
    print(json.dumps(res_logic.model_dump(), indent=2))
    print(f"\n[Verification] Thread ID resolved to: {res_logic.thread_id} (Expected: thread_general_456)")
    print(f"[Verification] Error Summary: '{res_logic.evidence.error_summary}'")
    print(f"[Verification] Error Hash: {res_logic.evidence.error_hash}")
    
    print("\n=== 3. WS Event Sequence ===")
    
    # Construct WS events manually to match what _notify_ws does
    ws_events = [
        # Compile (RECALL)
        {
            "type": "diagnosis_ready",
            "data": {
                "label": res_compile.err_type_pedagogical,
                "evidence": res_compile.evidence.natural_language,
                "recommendations": res_compile.recommendations,
                "spans": [s.model_dump() for s in res_compile.evidence.spans],
                "thread_id": res_compile.thread_id
            }
        },
        # Logic (MODIFICATION)
        {
            "type": "diagnosis_ready",
            "data": {
                "label": res_logic.err_type_pedagogical,
                "evidence": res_logic.evidence.natural_language,
                "recommendations": res_logic.recommendations,
                "spans": [s.model_dump() for s in res_logic.evidence.spans],
                "thread_id": res_logic.thread_id
            }
        }
    ]
    print(json.dumps(ws_events, indent=2))
    
    print("\n=== 4. Diagnosis Log Query (Latest 2) ===")
    logs = db.items
    for i, log in enumerate(logs):
        print(f"[{i}] ID={log.id} ThreadID={log.thread_id} Type={log.err_type_pedagogical} Conf={log.confidence}")
        
    print("\n=== 5. Frontend Render Log (Simulation) ===")
    print(f"[Frontend] WS Received: diagnosis_ready {{ label: '{res_compile.err_type_pedagogical}', thread_id: '{res_compile.thread_id}' }}")
    print(f"[Frontend] Rendering DiagnosisCard in Thread: {res_compile.thread_id}")
    print(f"[Frontend] WS Received: diagnosis_ready {{ label: '{res_logic.err_type_pedagogical}', thread_id: '{res_logic.thread_id}' }}")
    print(f"[Frontend] Rendering DiagnosisCard in Thread: {res_logic.thread_id}")

if __name__ == "__main__":
    asyncio.run(generate())
