
import requests
import sqlite3
import json
import time
import os
import sys
import difflib

# Configuration
BASE_URL = "http://127.0.0.1:8000/api/oracle"
DB_PATH = "backend.db"

# 1. Fixed Task Inputs (as per Checklist)
TASKS = [
    {
        "id": "T1",
        "name": "Repair Ops",
        "description": "Implement a repair ticket system. output_ops=['create', 'assign', 'resolve']. output_shape={'ticket_id': 'status'}. Return a dict mapping ticket IDs to status ('open', 'assigned', 'resolved'). Ignore invalid operations.",
        "deliverable": "function",
        "target_stage": "tests" # Analyze -> Confirm -> Tests
    },
    {
        "id": "T2",
        "name": "CLI Count",
        "description": "写一个 python CLI，从 stdin 读多行日志，每行格式 LEVEL | message（LEVEL=INFO/WARN/ERROR），忽略空行，输出三行：INFO/WARN/ERROR 的条数。",
        "deliverable": "cli",
        "target_stage": "tests" # Analyze -> Tests
    },
    {
        "id": "T3",
        "name": "Course Conflict",
        "description": "Check for scheduling conflicts. Input is a list of courses, each with a start and end time (integers). Return True if any two courses overlap, else False.",
        "deliverable": "function",
        "target_stage": "tests" # Analyze -> Tests
    },
    {
        "id": "T4",
        "name": "Intentional Failure",
        "description": "实现 solve(ops) ops_sequence，但我规定 output_ops 就是 [\"return\"]，并且 answers 的形状是单个 int（不是 list）。",
        "deliverable": "function",
        "target_stage": "analyze_fail" # Expect failure
    }
]

def safe_json_load(text):
    if not text: return None
    if isinstance(text, (dict, list)): return text
    try:
        return json.loads(text)
    except:
        return None

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def run_task_pipeline(task):
    print_section(f"Running Task: {task['name']} ({task['id']})")
    
    # 0. Create Task First
    print(f"[*] Creating task for {task['name']}...")
    try:
        t_resp = requests.post(f"{BASE_URL}/task", json={"project_id": "diagnosis_proj"})
        if t_resp.status_code != 200:
             print(f"[!] Create Task Failed: {t_resp.text}")
             return None
        task_id = t_resp.json()["task_id"]
        print(f"[+] Task Created: {task_id}")
    except Exception as e:
        print(f"[!] Create Task Request failed: {e}")
        return None

    # 1. Create Spec (Analyze)
    print(f"[*] Sending create_spec request...")
    payload = {
        "task_description": task["description"],
        "deliverable_type": task["deliverable"],
        "language": "python"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/task/{task_id}/version/spec", json=payload)
    except Exception as e:
        print(f"[!] Request failed: {e}")
        return None

    if resp.status_code == 422:
        print(f"[!] 422 Unprocessable Entity (Expected for T4?): {resp.text}")
        if task["target_stage"] == "analyze_fail":
            return {"task_id": "failed_req", "version_id": None, "status": "expected_fail", "error_resp": resp.json()}
        return None
    
    if resp.status_code != 200:
        print(f"[!] Error {resp.status_code}: {resp.text}")
        return None
        
    data = resp.json()
    version_id = data["version_id"]
    log_id = data["log_id"]
    
    # Check status via GET version to be sure
    v_resp = requests.get(f"{BASE_URL}/version/{version_id}")
    v_data = v_resp.json()
    status = v_data["status"]
    print(f"[+] Spec Created. Version: {version_id}, Status: {status}")
    
    # Stop if T4
    if task["target_stage"] == "analyze_fail":
        return {"task_id": "unknown", "version_id": version_id, "status": status}

    # 2. Confirm if needed (For T1)
    if status == "awaiting_confirmation":
        print(f"[*] Status is {status}. Attempting confirmation...")
        ambiguities = v_data.get("ambiguities", [])
        selections = {}
        for amb in ambiguities:
            aid = amb.get("ambiguity_id")
            choices = amb.get("choices", [])
            if choices:
                # Pick first choice
                cid = choices[0].get("choice_id")
                selections[aid] = cid
                print(f"    - Selecting {cid} for {aid}")
        
        c_resp = requests.post(f"{BASE_URL}/version/{version_id}/confirm", json={"selections": selections})
        if c_resp.status_code == 200:
            status = c_resp.json()["status"]
            print(f"[+] Confirmed. New Status: {status}")
        else:
            print(f"[!] Confirmation failed: {c_resp.text}")
            return {"task_id": "unknown", "version_id": version_id, "status": "confirm_failed"}

    # 3. Generate Tests (For T1, T2, T3)
    if task["target_stage"] == "tests":
        # Note: The API for generating tests is implicitly part of 'create_spec' in the current router?
        # Wait, looking at oracle.py, 'create_spec' calls 'mock_generate_spec'.
        # 'mock_generate_spec' seems to generate the spec. 
        # Where are tests generated?
        # In oracle.py: 
        # v = models.OracleTaskVersion(..., public_examples_json=public_examples_json, ...)
        # It seems tests (public examples) are generated AT THE SAME TIME as spec in create_spec.
        # But wait, there is a 'GenerateTestsBody' in oracle.py... let me check router again.
        # SearchCodebase showed 'GenerateTestsBody' but I didn't see the endpoint in the read output.
        # Let's assume for now they are generated in create_spec or we need to find the endpoint.
        # Re-reading oracle.py snippet: 
        # "public_examples_json = [e.model_dump() for e in spec.public_examples]"
        # So public examples ARE generated in create_spec.
        # What about hidden tests?
        # "hidden_tests_json: List[Dict[str, Any]] = []" -> They are initialized to empty in create_spec.
        # Is there a generate_tests endpoint?
        pass

    return {"task_id": "unknown", "version_id": version_id, "status": status}

def fetch_and_analyze(results):
    print_section("3. DB Export & 4. Field Diff")
    
    if not os.path.exists(DB_PATH):
        print("DB not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for i, task in enumerate(TASKS):
        res = results[i]
        print(f"\n--- Task {task['id']}: {task['name']} ---")
        
        if not res or not res.get("version_id"):
            print("No version ID (likely failed early).")
            # If T4, check logs or error response
            if task["id"] == "T4":
                print("T4 Intentional Failure Analysis:")
                print("Checking for raw data loss...")
                # We can't check DB if no version. 
                # But checklist asks to check 'status' of create_spec final state.
                if res and res.get("error_resp"):
                     print(f"API Response: {res['error_resp']}")
                continue
            continue

        vid = res["version_id"]
        cursor.execute("SELECT * FROM oracle_task_versions WHERE version_id = ?", (vid,))
        row = cursor.fetchone()
        
        if not row:
            print(f"Version {vid} not found in DB!")
            continue
            
        row = dict(row)
        
        # 3. Export Fields
        fields_to_export = [
            "status", "spec_json", "ambiguities_json", "user_confirmations_json", 
            "conflict_report_json", "spec_llm_raw_json", "llm_raw_spec_json",
            "spec_llm_request_id", "spec_prompt_version"
        ]
        
        # T2/T3 extras
        if task["id"] in ["T2", "T3"]:
            fields_to_export.extend([
                "public_examples_json", "hidden_tests_json", 
                "tests_llm_raw_json", "llm_raw_tests_json",
                "tests_llm_request_id", "tests_prompt_version"
            ])
            
        print("[DB Export]")
        for f in fields_to_export:
            val = row.get(f)
            val_str = str(val)
            # Truncate if too long, but keep key parts
            if val and isinstance(val, str) and len(val) > 200:
                print(f"  {f}: (len={len(val)}) {val[:100]}...{val[-50:]}")
            else:
                 print(f"  {f}: {val}")
        
        # 4.1 Spec Diff (Raw vs Spec)
        print("\n[Spec Diff Analysis]")
        raw_spec = safe_json_load(row.get("spec_llm_raw_json"))
        final_spec = safe_json_load(row.get("spec_json"))
        
        if not raw_spec:
            print("  (!) Raw spec is MISSING (NULL/Empty). Cannot perform diff.")
            print("  Conclusion: Observability Gap. Raw data was not persisted.")
        else:
            # Perform Diff
            diff_keys = ["interaction_model", "output_ops", "output_shape", "signature", "constraints", "assumptions", "deliverable", "runtime", "language"]
            for k in diff_keys:
                raw_val = raw_spec.get(k)
                final_val = final_spec.get(k)
                if raw_val != final_val:
                     print(f"  MISMATCH [{k}]:")
                     print(f"    Raw:   {raw_val}")
                     print(f"    Final: {final_val}")
                else:
                    print(f"  MATCH [{k}]")

        # 4.2 Tests Diff (T2/T3)
        if task["id"] in ["T2", "T3"]:
             print("\n[Tests Diff Analysis]")
             # TODO: Check raw tests if available
             raw_tests = safe_json_load(row.get("tests_llm_raw_json")) # or whatever column
             public_ex = safe_json_load(row.get("public_examples_json"))
             
             print(f"  Public Examples Count: {len(public_ex) if public_ex else 0}")
             if public_ex:
                 print("  Sample Expected Output:")
                 for idx, ex in enumerate(public_ex[:3]):
                     print(f"    #{idx}: {str(ex.get('expected'))[:50]}")

        # 6. Signature Check (T2)
        if task["id"] == "T2":
            print("\n[T2 Signature Source Check]")
            if raw_spec:
                print(f"  Raw Signature: {raw_spec.get('signature')}")
            else:
                print("  Raw Signature: <MISSING_RAW>")
            if final_spec:
                print(f"  Final Signature: {final_spec.get('signature')}")
    
    conn.close()

if __name__ == "__main__":
    results = []
    for task in TASKS:
        res = run_task_pipeline(task)
        results.append(res)
        time.sleep(1)
        
    fetch_and_analyze(results)
