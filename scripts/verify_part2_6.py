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
        # Create workspace if needed (simplified)
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
            
            # 3. Create Thread & Send Message
            t_res = requests.post(f"{BASE_URL}/api/threads", json={"session_id": session_id, "title": "Test Thread", "type": "global"})
            thread_id = t_res.json()["id"]
            log(f"Thread Created: {thread_id}")
            
            requests.post(f"{BASE_URL}/api/threads/{thread_id}/messages", json={"role": "user", "content": "Hello AI"})
            log("User message sent")
            
            # 4. Trigger Reply
            requests.post(f"{BASE_URL}/api/threads/{thread_id}/assistant_reply", json={"mode": "global", "include_code": False})
            log("Reply triggered, waiting for chunks...")
            
            # 5. Listen for Chunks
            chunks_received = 0
            full_content = ""
            message_ids = set()
            
            start_time = time.time()
            while time.time() - start_time < 5: # 5s timeout
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(msg)
                    # log(f"WS Recv: {data['type']}")
                    
                    if data["type"] == "ai_text_chunk":
                        chunk_content = data.get("chunk") or data.get("delta")
                        if chunk_content:
                            chunks_received += 1
                            full_content += chunk_content
                            message_ids.add(data["message_id"])
                            print(f"Chunk: {chunk_content}", end="", flush=True)
                    
                    if data["type"] == "ai_state" and data.get("state") == "done":
                        log("\nAI State: Done")
                        break
                        
                except asyncio.TimeoutError:
                    log("Timeout waiting for WS")
                    break
            
            # 6. Verify
            log("\n--- Verification ---")
            log(f"Chunks received: {chunks_received}")
            log(f"Unique Message IDs in chunks: {len(message_ids)} (Should be 1)")
            log(f"Full Content: {full_content}")
            
            if len(message_ids) == 1:
                log("PASS: Streaming used single message ID (No duplicate keys)")
            else:
                log(f"FAIL: Multiple message IDs used: {message_ids}")

    except Exception as e:
        log(f"WS Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
