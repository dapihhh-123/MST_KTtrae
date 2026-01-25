import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000/api"

def run_verify():
    print("=== Part 2.4 Verification ===")
    
    # 1. Create Workspace
    ws = requests.post(f"{BASE_URL}/workspaces", json={"name": "Verify2.4 WS"}).json()
    ws_id = ws["id"]
    
    # 2. Create Session
    print("\n[1] Testing Session Creation & General Thread...")
    sess = requests.post(f"{BASE_URL}/sessions", json={
        "workspace_id": ws_id,
        "title": "Integration Test"
    }).json()
    sess_id = sess["id"]
    print(f"Session Created: {sess_id}")
    
    # Get Threads
    threads = requests.get(f"{BASE_URL}/threads?session_id={sess_id}").json()
    print(f"GET /threads returned {len(threads)} threads.")
    print(json.dumps(threads, indent=2))
    
    general = next((t for t in threads if t["title"] == "General"), None)
    if general:
        print("✅ General thread found automatically.")
        if "summary" in general:
             print(f"✅ Summary field present: {general['summary']}")
    else:
        print("❌ General thread NOT found.")
        
    # 3. Message Flow
    print("\n[2] Testing Message Flow...")
    if general:
        tid = general["id"]
        msg_payload = {"content": "Hello Backend", "meta": {"ui_state": "focused"}}
        resp = requests.post(f"{BASE_URL}/threads/{tid}/messages/user", json=msg_payload)
        if resp.status_code == 200:
            msg = resp.json()
            print("✅ User message sent via /messages/user")
            print(json.dumps(msg, indent=2))
            
            # Verify persistence
            msgs = requests.get(f"{BASE_URL}/threads/{tid}/messages").json()
            found = any(m["id"] == msg["id"] for m in msgs)
            if found:
                print("✅ Message persisted and returned in GET list.")
            else:
                print("❌ Message NOT found in GET list.")
        else:
            print(f"❌ Failed to send message: {resp.text}")

    # 4. Breakout Creation
    print("\n[3] Testing Breakout Creation...")
    breakout_payload = {
        "title": "Refactor Loop",
        "anchor": {
            "file": "main.py",
            "line_start": 10,
            "line_end": 15,
            "code": "for i in range(10): pass"
        }
    }
    b_resp = requests.post(f"{BASE_URL}/sessions/{sess_id}/threads/breakout", json=breakout_payload)
    if b_resp.status_code == 200:
        breakout = b_resp.json()
        print("✅ Breakout created.")
        print(json.dumps(breakout, indent=2))
        
        # Verify it's in threads list
        threads_v2 = requests.get(f"{BASE_URL}/threads?session_id={sess_id}").json()
        b_in_list = next((t for t in threads_v2 if t["id"] == breakout["id"]), None)
        if b_in_list and b_in_list["type"] == "breakout":
            print("✅ Breakout appears in threads list with type='breakout'.")
    else:
        print(f"❌ Failed to create breakout: {b_resp.text}")

    # 5. Markers
    print("\n[4] Testing Markers API...")
    m_resp = requests.get(f"{BASE_URL}/markers?session_id={sess_id}")
    if m_resp.status_code == 200:
        markers = m_resp.json()
        print(f"GET /markers returned {len(markers)} markers.")
        print(json.dumps(markers, indent=2))
        
        # Verify linkage
        if len(markers) > 0:
            m = markers[0]
            if m["thread_id"] == breakout["id"] and m["line"] == 10:
                print("✅ Marker correctly links to breakout thread and line.")
    else:
         print(f"❌ Failed to get markers: {m_resp.text}")

    # 6. Code Snapshot
    print("\n[5] Testing Code Snapshot...")
    code_payload = {
        "content": "print('Updated Code')",
        "cursor_line": 5
    }
    c_resp = requests.post(f"{BASE_URL}/sessions/{sess_id}/code", json=code_payload)
    if c_resp.status_code == 200:
        print("✅ Code snapshot uploaded.")
        
        latest = requests.get(f"{BASE_URL}/sessions/{sess_id}/code/latest").json()
        print("GET /code/latest result:")
        print(json.dumps(latest, indent=2))
        if latest["content"] == code_payload["content"]:
             print("✅ Latest code matches uploaded content.")
    else:
        print(f"❌ Failed to upload code: {c_resp.text}")

if __name__ == "__main__":
    run_verify()
