import asyncio
import websockets
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"

async def listen_loop(ws, received_types, captured_chunks, captured_editor_ops, captured_error):
    try:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            msg_type = data.get('type')
            received_types.add(msg_type)
            
            print(f"WS RECV: {msg_type}")
            
            if msg_type == 'ai_text_chunk':
                if not captured_chunks:
                    if data.get('delta'):
                        captured_chunks.append(data)
                # print(f"CHUNK: {data.get('delta')}")
            
            elif msg_type == 'editor_ops':
                captured_editor_ops.append(data)
                
            elif msg_type == 'ai_state':
                state = data.get('state')
                print(f"STATE: {state}")
                if state == 'error':
                    captured_error.append(data)
                    print(f"ERROR DETAILS: {data}")
                if state == 'done':
                    print(f"DONE (thread={data.get('thread_id')})")
                    
    except websockets.exceptions.ConnectionClosed:
        print("WS Closed")
    except Exception as e:
        print(f"WS Listener Error: {e}")

async def demo_ws_flow():
    # 1. Get Default Session
    print("--- 1. Get Default Session ---")
    try:
        res = requests.get(f"{BASE_URL}/api/session/default")
        if res.status_code != 200:
            print(f"Failed to get session: {res.text}")
            return
        session_data = res.json()
        session_id = session_data["session_id"]
        print(f"Session Data: {json.dumps(session_data, indent=2)}")
    except Exception as e:
        print(f"Connection failed: {e}")
        return
    
    # 2. Connect WS
    print(f"\n--- 2. Connect WS: {session_id} ---")
    ws_url = f"{WS_BASE}/ws/session/{session_id}"
    
    received_types = set()
    captured_chunks = []
    captured_editor_ops = []
    captured_error = []
    
    async with websockets.connect(ws_url) as ws:
        print("WS Connected.")
        
        # Start listener task
        listener = asyncio.create_task(listen_loop(ws, received_types, captured_chunks, captured_editor_ops, captured_error))
        
        # 3. Trigger Mechanism (Manual Mode -> Forces Stream)
        print("\n--- 3. Trigger Mechanism (Manual Mode) ---")
        payload = {
            "session_id": session_id,
            "problem_id": 1,
            "mode": "manual" 
        }
        # Run in executor to avoid blocking loop
        loop = asyncio.get_running_loop()
        res_trig = await loop.run_in_executor(None, lambda: requests.post(f"{BASE_URL}/api/dev/trigger_mechanism", json=payload))
        print(f"Trigger Response: {res_trig.status_code}")
        
        # Wait a bit for stream
        await asyncio.sleep(5)

        # 5. Trigger AI Write
        print("\n--- 5. Trigger AI Write ---")
        payload_write = {
            "session_id": session_id,
            "instruction": "Fix the code",
            "target_range": {"start_line": 5, "start_col": 1, "end_line": 5, "end_col": 10}
        }
        res_write = await loop.run_in_executor(None, lambda: requests.post(f"{BASE_URL}/api/dev/ai_write_patch", json=payload_write))
        print(f"AI Write Response: {res_write.status_code}")
        
        await asyncio.sleep(2)
            
        # 7. Trigger Error (Invalid problem_id)
        print("\n--- 7. Trigger Error (Invalid problem_id) ---")
        payload_err = {
            "session_id": session_id,
            "problem_id": "invalid_int", 
            "mode": "manual"
        }
        try:
            await loop.run_in_executor(None, lambda: requests.post(f"{BASE_URL}/api/dev/trigger_mechanism", json=payload_err))
        except:
            pass
            
        await asyncio.sleep(2)
        
        # Cancel listener
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

    # 8. Verify Persistence
    print("\n--- 8. Verify Persistence ---")
    res_msgs = requests.get(f"{BASE_URL}/api/session/{session_id}/messages")
    print(f"GET messages status: {res_msgs.status_code}")
    
    last_assistant_msg = None
    if res_msgs.status_code == 200:
        messages = res_msgs.json()
        for m in reversed(messages):
            if isinstance(m, dict) and m.get('role') == 'assistant':
                last_assistant_msg = m
                break
            
    print("\n--- EVIDENCE DUMP ---")
    
    print("1. Received Types:")
    print(list(received_types))
    
    print("\n2. ai_text_chunk raw JSON:")
    if captured_chunks:
        print(json.dumps(captured_chunks[0], ensure_ascii=False))
    else:
        print("None captured")
        
    print("\n3. editor_ops raw JSON:")
    if captured_editor_ops:
        print(json.dumps(captured_editor_ops[0], ensure_ascii=False))
    else:
        print("None captured")
        
    print("\n4. Last Assistant Message:")
    if last_assistant_msg:
        print(json.dumps(last_assistant_msg, ensure_ascii=False))
    else:
        print("None found")
        
    print("\n5. ai_state=error raw JSON:")
    if captured_error:
        print(json.dumps(captured_error[0], ensure_ascii=False))
    else:
        print("None captured")

if __name__ == "__main__":
    asyncio.run(demo_ws_flow())
