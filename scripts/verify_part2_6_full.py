import asyncio
import websockets
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"

def log(msg):
    print(f"[TEST] {msg}")

async def verify():
    # 1. Init Session
    log("Initializing session...")
    try:
        ws_res = requests.post(f"{BASE_URL}/api/workspaces", json={"name": "TestWS"})
        ws_id = ws_res.json()["id"] if ws_res.ok else requests.get(f"{BASE_URL}/api/workspaces").json()[0]["id"]
        
        sess_res = requests.post(f"{BASE_URL}/api/sessions", json={"workspace_id": ws_id, "title": "TestSession"})
        session_id = sess_res.json()["id"]
        log(f"Session ID: {session_id}")
    except Exception as e:
        log(f"Session init failed: {e}")
        return

    # 2. Connect WS
    ws_url = f"{WS_BASE}/ws/session/{session_id}"
    log(f"Connecting WS: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            log("WS Connected (State: Open)")

            # --- EVIDENCE A: Debug Push ---
            log("\n--- Triggering Debug Push (Evidence A) ---")
            requests.post(f"{BASE_URL}/api/debug/push_test", json={"session_id": session_id})
            
            # Listen
            log("Listening for Debug events...")
            start_time = time.time()
            evidence_a_captured = False
            while time.time() - start_time < 5:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(msg)
                    print(f"WS Recv: {json.dumps(data)}")
                    if data["type"] == "ai_state" and data.get("state") == "done":
                        evidence_a_captured = True
                        break
                except asyncio.TimeoutError:
                    break
            
            if evidence_a_captured:
                log("✅ Evidence A Captured (Debug Sequence)")
            else:
                log("❌ Evidence A Missing")

            # --- EVIDENCE C: AI Write ---
            log("\n--- Triggering AI Write (Evidence C) ---")
            ai_write_payload = {
                "session_id": session_id,
                "instruction": "Rename variable x to count",
                "code_context": "def foo():\n    x = 0\n    return x",
                "target_range": {"start_line": 2, "end_line": 3}
            }
            resp = requests.post(f"{BASE_URL}/api/ai/write", json=ai_write_payload)
            log(f"AI Write Status: {resp.status_code}")
            if not resp.ok:
                log(f"AI Write Error: {resp.text}")
            
            log("Listening for AI Write events...")
            start_time = time.time()
            evidence_c_captured = False
            while time.time() - start_time < 10:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(msg)
                    print(f"WS Recv: {json.dumps(data)}")
                    if data["type"] == "editor_ops":
                        log("✅ Evidence C Captured (Editor Ops)")
                        evidence_c_captured = True
                    if data["type"] == "ai_state" and data.get("state") == "done":
                        break
                except asyncio.TimeoutError:
                    break
            
            if not evidence_c_captured:
                log("❌ Evidence C Missing")

            # --- EVIDENCE B: Streaming Reply ---
            log("\n--- Triggering Streaming Reply (Evidence B) ---")
            # Create Thread first
            t_res = requests.post(f"{BASE_URL}/api/threads", json={"session_id": session_id, "title": "Stream Test", "type": "global"})
            thread_id = t_res.json()["id"]
            requests.post(f"{BASE_URL}/api/threads/{thread_id}/messages", json={"role": "user", "content": "Count to 3"})
            
            requests.post(f"{BASE_URL}/api/threads/{thread_id}/assistant_reply", json={"mode": "global", "include_code": False})
            
            log("Listening for Streaming Reply...")
            start_time = time.time()
            chunks = 0
            while time.time() - start_time < 10:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(msg)
                    if data["type"] == "ai_text_chunk":
                        chunks += 1
                        print(f"Chunk: {data.get('delta') or data.get('chunk')}", end="", flush=True)
                    if data["type"] == "ai_state" and data.get("state") == "done":
                        break
                except asyncio.TimeoutError:
                    break
            print() # Newline
            if chunks > 0:
                log(f"✅ Evidence B Captured ({chunks} chunks)")
            else:
                log("❌ Evidence B Missing")

    except Exception as e:
        log(f"WS Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
