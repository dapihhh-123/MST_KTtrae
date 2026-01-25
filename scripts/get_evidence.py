import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def get_evidence():
    # 1. Session Default
    res1 = requests.get(f"{BASE_URL}/api/session/default")
    session_data = res1.json()
    print("### 1. GET /api/session/default Response")
    print(json.dumps(session_data, indent=2))
    
    session_id = session_data["session_id"]
    
    # 2. Trigger Mechanism
    payload2 = {
        "session_id": session_id,
        "problem_id": 1,
        "mode": "manual"
    }
    res2 = requests.post(f"{BASE_URL}/api/dev/trigger_mechanism", json=payload2)
    print("\n### 3. POST /api/dev/trigger_mechanism Response")
    print(json.dumps(res2.json(), indent=2))
    
    # 3. AI Write Patch
    payload3 = {
        "session_id": session_id,
        "instruction": "fix",
        "target_range": {"start_line": 1, "start_col": 1, "end_line": 2, "end_col": 1}
    }
    res3 = requests.post(f"{BASE_URL}/api/dev/ai_write_patch", json=payload3)
    print("\n### 4. POST /api/dev/ai_write_patch Response")
    print(json.dumps(res3.json(), indent=2))

if __name__ == "__main__":
    get_evidence()
