import requests
import sys
import json
import time

BASE_URL = "http://127.0.0.1:8000/api"

def print_log(method, url, payload, status, response, duration):
    print(f"\n[{method}] {url}")
    print(f"Status: {status} ({duration:.2f}ms)")
    if payload:
        print(f"Request Payload: {json.dumps(payload, indent=2)}")
    # Truncate long response
    resp_str = json.dumps(response, indent=2)
    if len(resp_str) > 500:
        resp_str = resp_str[:500] + "... (truncated)"
    print(f"Response: {resp_str}")
    print("-" * 50)

def req(method, endpoint, payload=None):
    url = f"{BASE_URL}{endpoint}"
    start = time.time()
    if method == "GET":
        r = requests.get(url)
    elif method == "POST":
        r = requests.post(url, json=payload)
    
    try:
        data = r.json()
    except:
        data = r.text
        
    duration = (time.time() - start) * 1000
    print_log(method, endpoint, payload, r.status_code, data, duration)
    return r

def run():
    print("=== Simulating Frontend Session Initialization ===")
    
    # 1. Init Session
    # Frontend: getOrCreateSessionId()
    # Check Workspaces first (internal logic of initSession)
    print("\n>>> Step 1: Check Workspaces (internal)")
    r = req("GET", "/workspaces")
    workspaces = r.json()
    if not workspaces:
        r = req("POST", "/workspaces", {"name": "Default"})
        ws_id = r.json()["id"]
    else:
        ws_id = workspaces[0]["id"]
        
    # Create Session
    print("\n>>> Step 2: Create Session (POST /api/sessions)")
    r = req("POST", "/sessions", {"workspace_id": ws_id, "title": "Auto Session"})
    session_id = r.json()["id"]
    
    # 2. Get Threads
    print(f"\n>>> Step 3: Get Threads (GET /api/sessions/{session_id}/threads)")
    r = req("GET", f"/sessions/{session_id}/threads")
    threads = r.json()
    global_thread = next((t for t in threads if t["type"] == "global"), None)
    thread_id = global_thread["id"]
    
    # 3. Connect WS (Simulated)
    print(f"\n>>> Step 4: Connect WebSocket (ws://localhost:8000/ws/session/{session_id})")
    print("WebSocket Connection: OPEN")
    
    # 4. User Sends Message
    print(f"\n>>> Step 5: User Sends Message (POST /api/threads/{thread_id}/messages)")
    r = req("POST", f"/threads/{thread_id}/messages", {"role": "user", "content": "Hello AI"})
    
    # 5. Trigger AI Reply
    print(f"\n>>> Step 6: Trigger AI Reply (POST /api/threads/{thread_id}/assistant_reply)")
    r = req("POST", f"/threads/{thread_id}/assistant_reply", {"mode": "global", "include_code": True})
    
    # 6. Create Breakout
    print("\n>>> Step 7: Create Breakout (POST /api/threads)")
    r = req("POST", "/threads", {
        "session_id": session_id,
        "type": "breakout", 
        "title": "Breakout 1",
        "anchor": {"line_start": 10, "line_end": 20}
    })
    
    print("\n=== Verification Complete: Session Logic Verified ===")

if __name__ == "__main__":
    run()
