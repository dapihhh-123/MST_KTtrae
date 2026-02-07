import os
import sys
import time
import requests
import json
import logging

# Configuration
BASE_URL = "http://localhost:8001/api"
LOG_FILE = "verify_offline_97.log"

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(message)s')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

def log(msg):
    logging.info(msg)

def run_task(task_def, run_label):
    url = f"{BASE_URL}/oracle/task"
    try:
        # Create Task
        resp = requests.post(url, json={"project_id": f"verify_{run_label}"})
        if resp.status_code != 200:
            log(f"FAIL: Create task failed {resp.status_code} {resp.text}")
            return None
        task_id = resp.json()["task_id"]
        
        # Create Spec (Analyze)
        spec_body = {
            "task_description": task_def["desc"],
            "deliverable_type": task_def["deliverable"],
            "language": "python",
            "runtime": "python"
        }
        
        t0 = time.time()
        resp = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=spec_body)
        latency = (time.time() - t0) * 1000
        
        if resp.status_code != 200:
            # Handle expected failures (if any)
            return {"status": "analyze_failed", "error": resp.text, "attempts": 0}
            
        data = resp.json()
        
        # Get Debug Info
        debug_resp = requests.get(f"{BASE_URL}/oracle/debug/last_spec_call")
        debug_data = debug_resp.json()
        
        return {
            "status": data["spec_summary"].get("status", "unknown") if "spec_summary" in data else "ready", # spec_summary doesn't have status, version does.
            # Wait, the spec creation returns SpecResp which has spec_summary, but status is on Version.
            # SpecResp definition: version_id, spec_summary, ambiguities, oracle_confidence_initial, ...
            # We need to get the version to see the status (ready/low_confidence)
            "version_id": data["version_id"],
            "ambiguities": data.get("ambiguities", []),
            "spec_summary": data.get("spec_summary", {}),
            "debug": debug_data
        }
    except Exception as e:
        log(f"EXCEPTION: {e}")
        return None

def get_version_status(version_id):
    resp = requests.get(f"{BASE_URL}/oracle/version/{version_id}")
    if resp.status_code == 200:
        return resp.json()
    return {}

def main():
    log("=== Analyze Stage 90%->97% Functional Verification (Offline) ===")
    
    # A1: Preflight
    log("\n--- A. Preflight ---")
    try:
        debug_cfg = requests.get(f"{BASE_URL}/oracle/debug/config").json()
        log(f"Config: {json.dumps(debug_cfg, indent=2)}")
        # Check if we are in mock mode? The debug config might not reflect the env var if it wasn't explicitly wired to the config dict.
        # But we can verify by running a task and checking the provider.
    except Exception as e:
        log(f"FAIL: Could not connect to backend: {e}")
        return

    # B1: Deterministic Drift (Clear Tasks)
    log("\n--- B1. Deterministic Drift (Clear Tasks) ---")
    scenarios = [
        {"name": "Clear CLI", "desc": "mock_clear_cli", "deliverable": "cli", "expected_model": "cli_stdio"},
        {"name": "Clear Func", "desc": "mock_clear_func", "deliverable": "function", "expected_model": "function_single"},
        {"name": "Clear Ops", "desc": "mock_clear_ops", "deliverable": "function", "expected_model": "stateful_ops"},
    ]
    
    b1_pass = True
    for sc in scenarios:
        log(f"Running {sc['name']} (20 runs)...")
        failures = 0
        models_pred = []
        for i in range(20):
            res = run_task(sc, f"b1_{i}")
            if not res:
                failures += 1
                continue
            
            if res.get("status") == "analyze_failed":
                failures += 1
                log(f"  Run {i}: FAILED (Analyze Failed)")
                continue

            v_data = get_version_status(res["version_id"])
            status = v_data.get("status")
            model = res["debug"].get("interaction_model_pred")
            models_pred.append(model)
            
            if status == "analyze_failed":
                failures += 1
                log(f"  Run {i}: FAILED")
            
        uniq_models = set(models_pred)
        log(f"  Result: Failures={failures}, Models={uniq_models}")
        if failures > 0 or len(uniq_models) > 1 or sc["expected_model"] not in uniq_models:
            b1_pass = False
            log("  -> FAIL")
        else:
            log("  -> PASS")

    # B2: Deterministic Drift (Ambiguous)
    log("\n--- B2. Deterministic Drift (Ambiguous) ---")
    amb_scenario = {"name": "Ambiguous", "desc": "mock_ambiguous", "deliverable": "function"}
    amb_pass = True
    log(f"Running Ambiguous (20 runs)...")
    amb_stats = []
    for i in range(20):
        res = run_task(amb_scenario, f"b2_{i}")
        if not res: continue
        v_data = get_version_status(res["version_id"])
        amb_stats.append((v_data.get("status"), len(v_data.get("ambiguities", [])), v_data.get("spec_summary", {}).get("signature", {}).get("returns")))
    
    # Check consistency
    uniq_stats = set(amb_stats)
    log(f"  Stats (Status, Ambs, Returns): {uniq_stats}")
    if len(uniq_stats) == 1 and list(uniq_stats)[0] == ('low_confidence', 1, 'Any'):
        log("  -> PASS")
    else:
        amb_pass = False
        log("  -> FAIL")

    # D1: Quality Check
    log("\n--- D1. Spec Quality Check ---")
    # We check the last run of B1 scenarios
    d1_pass = True
    # Just run one check per scenario type
    for sc in scenarios:
        res = run_task(sc, "d1_quality")
        v_data = get_version_status(res["version_id"])
        examples = v_data.get("public_examples", [])
        if len(examples) < 1:
            log(f"  FAIL: {sc['name']} has no examples")
            d1_pass = False
        else:
            ex = examples[0]
            if "input" not in ex or "expected" not in ex:
                 log(f"  FAIL: {sc['name']} example malformed")
                 d1_pass = False
            else:
                 log(f"  PASS: {sc['name']} has valid examples")
    
    # E1: Error Injection
    log("\n--- E1. Error Injection ---")
    
    # Case 1: JSON Fail -> Repair
    log("Running E1_JSON_FAIL...")
    res_json = run_task({"desc": "trigger_json_fail", "deliverable": "function"}, "e1_json")
    v_json = get_version_status(res_json["version_id"])
    attempts_json = res_json["debug"].get("attempts")
    log(f"  JSON Fail Result: Status={v_json.get('status')}, Attempts={attempts_json}")
    if v_json.get('status') in ["ready", "low_confidence"] and attempts_json > 1:
        log("  -> PASS (Repaired)")
    else:
        log("  -> FAIL (Did not repair or not enough attempts)")
        
    # Case 2: Type Mismatch -> Fallback
    log("Running E1_TYPE_MISMATCH...")
    res_type = run_task({"desc": "trigger_type_mismatch", "deliverable": "function"}, "e1_type")
    v_type = get_version_status(res_type["version_id"])
    attempts_type = res_type["debug"].get("attempts")
    fail_reasons = res_type["debug"].get("fail_reasons", [])
    log(f"  Type Fail Result: Status={v_type.get('status')}, Attempts={attempts_type}, Reasons={fail_reasons}")
    # In mock, we assume the repair loop fixes it or fallback triggers. 
    # Since I didn't implement a complex stateful mock that changes behavior on retries for type mismatch (only checking "fix signature" hint),
    # let's see if the logic holds.
    if v_type.get('status') in ["ready", "low_confidence"]:
         log("  -> PASS (Handled)")
    else:
         log("  -> FAIL")

    # Summary
    log("\n=== Final Report ===")
    log(f"B1 Clear Drift: {'PASS' if b1_pass else 'FAIL'}")
    log(f"B2 Ambiguous Drift: {'PASS' if amb_pass else 'FAIL'}")
    log(f"D1 Quality: {'PASS' if d1_pass else 'FAIL'}")
    
    score = 100
    deductions = []
    if not b1_pass: 
        score -= 20
        deductions.append("B1: Deterministic clear tasks failed")
    if not amb_pass:
        score -= 10
        deductions.append("B2: Ambiguous tasks inconsistent")
    if not d1_pass:
        score -= 5
        deductions.append("D1: Spec quality check failed")
    
    log(f"Score: {score}%")
    for d in deductions:
        log(f"- {d}")

if __name__ == "__main__":
    main()
