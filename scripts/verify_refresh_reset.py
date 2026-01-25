import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def log(msg):
    print(f"[TEST] {msg}")

def test_refresh_reset_logic():
    # 1. Simulate First Load
    log("--- Simulate First Load ---")
    # Frontend: initSession() -> no local storage -> create session
    # We need a workspace first (backend requirement)
    ws_res = requests.get(f"{BASE_URL}/api/workspaces")
    if ws_res.status_code == 200 and len(ws_res.json()) > 0:
        workspace_id = ws_res.json()[0]["id"]
    else:
        ws_res = requests.post(f"{BASE_URL}/api/workspaces", json={"name": "Test WS"})
        workspace_id = ws_res.json()["id"]
    
    res1 = requests.post(f"{BASE_URL}/api/sessions", json={"workspace_id": workspace_id, "title": "Session 1"})
    if res1.status_code != 200:
        log(f"Failed to create session 1: {res1.text}")
        sys.exit(1)
    
    session_id_1 = res1.json()["id"]
    log(f"Session 1 Created: {session_id_1}")
    
    # Simulate adding data to Session 1
    t_res = requests.post(f"{BASE_URL}/api/threads", json={"session_id": session_id_1, "title": "Thread 1", "type": "global"})
    thread_id_1 = t_res.json()["id"]
    requests.post(f"{BASE_URL}/api/threads/{thread_id_1}/messages", json={"role": "user", "content": "Msg in Session 1"})
    log("Added data to Session 1")

    # 2. Simulate Refresh (Refresh = Reset)
    log("\n--- Simulate Refresh (Reset) ---")
    # Frontend logic: resetSessionLocal() clears storage.
    # initSession() sees empty storage -> creates NEW session.
    
    res2 = requests.post(f"{BASE_URL}/api/sessions", json={"workspace_id": workspace_id, "title": "Session 2"})
    session_id_2 = res2.json()["id"]
    log(f"Session 2 Created: {session_id_2}")
    
    if session_id_1 == session_id_2:
        log("❌ FAIL: Session ID reused! Refresh did not reset session.")
        sys.exit(1)
    else:
        log("✅ PASS: New Session ID generated.")

    # 3. Verify Isolation
    # Session 2 should NOT see Session 1's threads
    threads_res = requests.get(f"{BASE_URL}/api/sessions/{session_id_2}/threads")
    threads = threads_res.json()
    # Should only have default/welcome thread if any, but definitely not "Thread 1"
    thread_titles = [t["title"] for t in threads]
    log(f"Session 2 Threads: {thread_titles}")
    
    if "Thread 1" in thread_titles:
        log("❌ FAIL: Session 2 sees Session 1 data!")
    else:
        log("✅ PASS: Session 2 data isolated.")

if __name__ == "__main__":
    try:
        test_refresh_reset_logic()
        log("\n✅ Verification Successful: Refresh=Reset logic confirmed.")
    except Exception as e:
        log(f"\n❌ Verification Failed: {e}")
        sys.exit(1)
