import requests
import concurrent.futures
import time
import json
import sqlite3

BASE_URL = "http://localhost:8001/api"
HEADERS = {"Content-Type": "application/json"}
DB_PATH = "backend.db"

def create_and_analyze(idx):
    task_desc = f"Concurrent Task {idx}: Write a function to calculate factorial of {idx}."
    req_body = {
        "task_description": task_desc,
        "deliverable_type": "function",
        "language": "python",
        "runtime": "python"
    }
    
    try:
        # Create Task
        t0 = time.time()
        resp = requests.post(f"{BASE_URL}/oracle/task", json={"project_id": f"conc_{idx}"}, headers=HEADERS)
        if resp.status_code != 200:
            return {"idx": idx, "status": "fail_create", "error": resp.text}
        task_id = resp.json().get("task_id")
        
        # Analyze
        resp = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=req_body, headers=HEADERS)
        t1 = time.time()
        
        if resp.status_code != 200:
            return {"idx": idx, "status": "fail_analyze", "error": resp.text}
            
        data = resp.json()
        version_id = data.get("version_id")
        return {
            "idx": idx,
            "status": "success",
            "version_id": version_id,
            "latency": t1 - t0
        }
    except Exception as e:
        return {"idx": idx, "status": "error", "error": str(e)}

def check_db_persistence(version_ids):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(version_ids))
    cursor.execute(f"SELECT version_id, spec_llm_request_id FROM oracle_task_versions WHERE version_id IN ({placeholders})", version_ids)
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def run_concurrency_test():
    print("Starting E1. 20 concurrent Analyze calls...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(create_and_analyze, i) for i in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"Success rate: {success_count}/20")
    
    if success_count < 20:
        print("FAIL: Not all requests succeeded.")
        for r in results:
            if r["status"] != "success":
                print(f"  - {r}")
        return

    version_ids = [r["version_id"] for r in results]
    unique_versions = set(version_ids)
    print(f"Unique version_ids: {len(unique_versions)}/20")
    
    if len(unique_versions) != 20:
        print("FAIL: Duplicate version_ids detected.")
        return

    # Check persistence
    db_map = check_db_persistence(version_ids)
    print(f"DB persistence check: {len(db_map)}/20 found.")
    
    missing_req_ids = [v for v, req in db_map.items() if not req]
    if missing_req_ids:
        print(f"FAIL: Missing request_id for versions: {missing_req_ids}")
    else:
        print("PASS: All versions have request_id in DB.")

if __name__ == "__main__":
    run_concurrency_test()
