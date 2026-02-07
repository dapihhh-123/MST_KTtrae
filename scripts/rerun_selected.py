
import json
import requests
import time
import sqlite3
import sys

BASE_URL = "http://127.0.0.1:8001/api/oracle"
DB_PATH = "backend.db"

TASKS = [
    # 1. Ops Sequence (Must produce solve(ops))
    {
        "id": "OPS_001",
        "task_description": "Implement a ticketing system. Operations: create, update, delete. Handle status changes. Return results of operations.",
        "deliverable": "function"
    },
    # 2. CLI (Must produce stdin/stdout specs)
    {
        "id": "CLI_001",
        "task_description": "CLI tool that reads a list of numbers from stdin (one per line) and prints the sum to stdout.",
        "deliverable": "cli"
    },
    # 3. Data Processing (Function single)
    {
        "id": "DATA_001",
        "task_description": "Write a function filter_large_numbers(data) that returns a list of numbers greater than 100.",
        "deliverable": "function"
    },
    # 4. Mixed (Messy but valid)
    {
        "id": "MIX_001",
        "task_description": "Task: 实现一个 Cache. Keys are strings. Methods: get(k), set(k,v). Requirement: O(1) time complexity.",
        "deliverable": "function"
    },
    # 5. Underspecified (Ambiguous)
    {
        "id": "AMB_001",
        "task_description": "Process the user list to improve performance.",
        "deliverable": "function"
    },
    # 6. Confusable 1 (Ops-like but Single)
    {
        "id": "OPS_005", # Confusable
        "task_description": "Write a function that takes a list of operations [add, sub] and returns the single final result value.",
        "deliverable": "function"
    },
    # 7. Confusable 2 (CLI-like but Function)
    {
        "id": "CLI_005", # Confusable
        "task_description": "Write a function that parses command line arguments string and returns a config dict.",
        "deliverable": "function"
    }
]

def get_db_trace(task_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                llm_provider_used, 
                llm_model_used, 
                attempts, 
                status,
                interaction_model_pred,
                spec_llm_request_id,
                llm_latency_ms
            FROM oracle_task_versions 
            WHERE task_id = ? 
            ORDER BY created_at DESC LIMIT 1
        """, (task_id,))
        row = cursor.fetchone()
    except Exception as e:
        print(f"DB Error: {e}")
        row = None
        
    conn.close()
    if row:
        return {
            "provider": row[0],
            "model": row[1],
            "attempts": row[2],
            "status": row[3],
            "interaction_model": row[4],
            "request_id": row[5],
            "latency": row[6]
        }
    return None

def run():
    print(f"Running Selected Benchmark on {len(TASKS)} tasks...")
    
    # Ensure backend is up
    try:
        requests.get(f"{BASE_URL.replace('/api/oracle', '')}/health")
    except:
        print("Backend not reachable. Start it first.")
        return

    results = []

    with open("benchmark_logs.txt", "w") as log_file:
        for t in TASKS:
            start = time.time()
            
            # 1. Create Task
            try:
                # Remove task_id from payload as API doesn't allow it
                resp = requests.post(f"{BASE_URL}/task", json={"project_id": "bench"}) 
                
                if resp.status_code == 200:
                    real_task_id = resp.json()["task_id"]
                else:
                    print(f"Task Create Failed: {resp.status_code} {resp.text}")
                    real_task_id = "unknown"
                
                # 2. Create Spec (Real LLM)
                payload = {
                    "task_description": t["task_description"],
                    "deliverable_type": t["deliverable"],
                    "debug_invalid_mock": False
                }
                
                trace = None
                if real_task_id != "unknown":
                    resp = requests.post(f"{BASE_URL}/task/{real_task_id}/version/spec", json=payload)
                    if resp.status_code != 200:
                        print(f"Spec Create Failed: {resp.status_code} {resp.text}")
                    
                    time.sleep(2) # Allow DB commit flush
                    
                    # Fetch DB Trace
                    trace = get_db_trace(real_task_id)
                
                if not trace:
                    trace = {"provider": "unknown", "model": "unknown", "attempts": 0, "status": "fail", "interaction_model": "unknown"}
                
                # Log Line (H5 Requirement)
                log_line = f"[RUN] {t['id']} provider={trace.get('provider')} model={trace.get('model')} request_id={trace.get('request_id')} latency_ms={trace.get('latency')} status={trace.get('status')}"
                print(log_line)
                log_file.write(log_line + "\n")
                
                # Store map for evidence generator
                results.append({
                    "test_id": t["id"],
                    "real_task_id": real_task_id,
                    "trace": trace
                })
                
            except Exception as e:
                print(f"[RUN] {t['id']} Error: {e}")

    with open("selected_benchmark_map.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run()
