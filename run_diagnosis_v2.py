
import requests
import sqlite3
import json
import time
import os
import sys

# Configuration
BASE_URL = "http://127.0.0.1:8001/api/oracle"
DB_PATH = "backend.db"

# 1. Fixed Task Inputs
TASKS = [
    {
        "id": "T1",
        "name": "Repair Ops",
        # Translating to Chinese as requested by strict checklist
        "description": "实现一个报修单系统。output_ops=['create', 'assign', 'resolve']。output_shape={'ticket_id': 'status'}。返回一个字典，映射 ticket_id 到 status（'open', 'assigned', 'resolved'）。忽略非法操作。",
        "deliverable": "function",
        "target_stage": "run" # spec -> confirm -> generate-tests -> run
    },
    {
        "id": "T2",
        "name": "CLI Count",
        "description": "写一个 python CLI，从 stdin 读多行日志，每行格式 LEVEL | message（LEVEL=INFO/WARN/ERROR），忽略空行，输出三行：INFO/WARN/ERROR 的条数。",
        "deliverable": "cli",
        "target_stage": "run" # spec -> generate-tests -> run
    },
    {
        "id": "T3",
        "name": "Course Conflict",
        "description": "Check for scheduling conflicts. Input is a list of courses, each with a start and end time (integers). Return True if any two courses overlap, else False.",
        "deliverable": "function",
        "target_stage": "tests"
    },
    {
        "id": "T4",
        "name": "Intentional Failure",
        "description": "实现 solve(ops) ops_sequence，但我规定 output_ops 就是 [\"return\"]，并且 answers 的形状是单个 int（不是 list）。",
        "deliverable": "function",
        "target_stage": "analyze_fail"
    },
    {
        "id": "T5",
        "name": "Ambiguous Task",
        "description": "我要做一个简单的任务管理器，能添加任务、完成任务、查任务。输入是一堆操作，输出是我每次查询的结果。ID 是数字，查的时候要按 ID 从小到大。别的你自己合理补齐。",
        "deliverable": "function",
        "target_stage": "analyze_fail" # Likely needs clarification
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
    # Retry loop
    for attempt in range(3):
        try:
            t_resp = requests.post(f"{BASE_URL}/task", json={"project_id": "diagnosis_proj"})
            if t_resp.status_code == 200:
                break
            time.sleep(1)
        except Exception as e:
            print(f"    Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    else:
        print(f"[!] Create Task Failed after retries")
        return None

    try:
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
            # For T4, we might not get a version_id if it fails validation BEFORE saving to DB?
            # But the router code saves to DB if it's a validation error? 
            # No, 'TaskSpec.model_validate' raises ValidationError -> HTTPException.
            # But it logs it. 
            # It seems it does NOT create a DB entry if model_validate fails?
            # Wait, line 236 in oracle.py creates the version.
            # But line 218 validates it.
            # If validation fails, it raises 422 and DOES NOT save the version.
            # This explains why T4 might be missing from DB if it fails Pydantic validation.
            # But we need to check if 'spec_llm_raw_json' is saved somewhere?
            # If it fails before DB insert, then it's definitely NOT in DB.
            return {"task_id": task_id, "version_id": None, "status": "schema_fail", "error_resp": resp.json()}
        return None
    
    if resp.status_code != 200:
        print(f"[!] Error {resp.status_code}: {resp.text}")
        return None
        
    data = resp.json()
    version_id = data["version_id"]
    log_id = data["log_id"]
    
    # Check status via GET version
    v_resp = requests.get(f"{BASE_URL}/version/{version_id}")
    v_data = v_resp.json()
    status = v_data["status"]
    print(f"[+] Spec Created. Version: {version_id}, Status: {status}")
    
    if task["target_stage"] == "analyze_fail":
        return {"task_id": task_id, "version_id": version_id, "status": status}

    # 2. Confirm if needed (For T1 or others)
    if status == "awaiting_confirmation" or status == "low_confidence":
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
        
        # Even if no ambiguities, we might need to confirm if low_confidence?
        # The code says if status != low_confidence, set to ready.
        c_resp = requests.post(f"{BASE_URL}/version/{version_id}/confirm", json={"selections": selections})
        if c_resp.status_code == 200:
            status = c_resp.json()["status"]
            print(f"[+] Confirmed. New Status: {status}")
        else:
            print(f"[!] Confirmation failed: {c_resp.text}")
            return {"task_id": task_id, "version_id": version_id, "status": "confirm_failed"}

    # 3. Generate Tests (For T1, T2, T3)
    if task["target_stage"] in ["tests", "run"]:
        print(f"[*] Generating Tests for {version_id}...")
        gen_payload = {
            "public_examples_count": 5,
            "hidden_tests_count": 5
        }
        g_resp = requests.post(f"{BASE_URL}/version/{version_id}/generate-tests", json=gen_payload)
        
        if g_resp.status_code == 200:
            g_data = g_resp.json()
            print(f"[+] Tests Generated. Status: {g_data['status']}")
            print(f"    Public: {len(g_data.get('public_examples_preview', []))} Hidden: {g_data.get('hidden_tests_count')}")
        else:
            print(f"[!] Generate Tests Failed: {g_resp.text}")

    # 4. Run (For T1, T2)
    if task["target_stage"] == "run":
        print(f"[*] Running Tests for {version_id}...")
        
        # 4.1 Fail Run
        print("    [4.1] Triggering Failure...")
        fail_code = "def solve(ops): return []" if task["deliverable"] == "function" else "print('error')"
        run_payload = {
            "code_text": fail_code,
            "timeout_sec": 2.0
        }
        r_resp = requests.post(f"{BASE_URL}/version/{version_id}/run", json=run_payload)
        if r_resp.status_code == 200:
             r_data = r_resp.json()
             print(f"    [+] Run Completed. Pass Rate: {r_data['pass_rate']}")
        else:
             print(f"    [!] Run Failed: {r_resp.text}")

        # 4.2 Success Run (Mock)
        print("    [4.2] Triggering Success (Mock)...")
        # Note: We don't have the actual solution, so this will likely fail too, but distinct from 4.1
        # For T2 (CLI Count), we can try a simple script
        success_code = fail_code
        if task["id"] == "T2":
             success_code = "import sys\nfor line in sys.stdin:\n    pass\nprint('INFO: 0')\nprint('WARN: 0')\nprint('ERROR: 0')"
        
        run_payload["code_text"] = success_code
        r_resp = requests.post(f"{BASE_URL}/version/{version_id}/run", json=run_payload)
        if r_resp.status_code == 200:
             r_data = r_resp.json()
             print(f"    [+] Run Completed. Pass Rate: {r_data['pass_rate']}")

    return {"task_id": task_id, "version_id": version_id, "status": status}

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
        
        if not res:
            print("No result object.")
            continue
            
        vid = res.get("version_id")
        
        if not vid:
            print("No version ID (likely failed schema validation).")
            if task["id"] == "T4":
                print("T4 Intentional Failure Analysis:")
                print("  Check: Did we get a 422? Yes." if res.get("status") == "schema_fail" else "  Check: Unknown error.")
                # We cannot check DB for version if it wasn't created.
                # But we should check if there are ANY versions for this task?
                # Actually, in 'create_spec', if validation fails, it RAISES exception and does NOT save.
                # So 'spec_llm_raw_json' is indeed LOST if validation fails.
            continue

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
            "spec_llm_request_id", "spec_prompt_version",
            # Extra fields if available (check keys)
            "llm_provider_used", "llm_model_used", "llm_latency_ms", "llm_attempts", "cache_hit"
        ]
        
        # T2/T3 extras
        if task["id"] in ["T2", "T3"]:
            fields_to_export.extend([
                "public_examples_json", "hidden_tests_json", 
                "tests_llm_raw_json", "llm_raw_tests_json",
                "tests_llm_request_id", "tests_prompt_version"
            ])
            
        print("[DB Export]")
        row_keys = row.keys()
        for f in fields_to_export:
            if f not in row_keys:
                print(f"  {f}: <NOT_IN_SCHEMA>")
                continue
                
            val = row.get(f)
            val_str = str(val)
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
            diff_keys = ["interaction_model", "output_ops", "output_shape", "signature", "constraints", "assumptions"]
            for k in diff_keys:
                raw_val = raw_spec.get(k)
                final_val = final_spec.get(k)
                
                # Normalize for comparison if needed
                if raw_val != final_val:
                     print(f"  MISMATCH [{k}]:")
                     print(f"    Raw:   {raw_val}")
                     print(f"    Final: {final_val}")
                else:
                    print(f"  MATCH [{k}]")

        # 4.2 Tests Diff (T2/T3)
        if task["id"] in ["T2", "T3"]:
             print("\n[Tests Diff Analysis]")
             raw_tests = safe_json_load(row.get("tests_llm_raw_json")) # or whatever column
             public_ex = safe_json_load(row.get("public_examples_json"))
             
             print(f"  Public Examples Count: {len(public_ex) if public_ex else 0}")
             if public_ex:
                 print("  Sample Expected Output:")
                 for idx, ex in enumerate(public_ex[:3]):
                     print(f"    #{idx}: {str(ex.get('expected'))[:50]}")
             
             # Check if raw tests exists
             if not row.get("tests_llm_raw_json") and not row.get("llm_raw_tests_json"):
                 print("  (!) Raw tests JSON is NULL.")
                 req_id = row.get("tests_llm_request_id")
                 if req_id:
                     print(f"  But tests_llm_request_id is present: {req_id}. LLM WAS called.")
                 else:
                     print("  tests_llm_request_id is ALSO NULL. LLM might not have been called (or mocking used).")

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
