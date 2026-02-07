
import requests
import json
import time
import sqlite3
import os

BASE_URL = "http://localhost:8001/api"
HEADERS = {"Content-Type": "application/json"}
DB_PATH = "backend.db"
OUTPUT_FILE = "r5_fix_evidence.txt"

TASKS = [
    {
        "id": "R5",
        "desc": "ops 可能既是 list 格式，也可能是字符串命令（例如 `\"ADD 1 hello\"`）。你需要决定是否支持两种格式，或者只支持一种并写 assumptions。\n另外：输出要求不明确，请你生成歧义让用户选择“返回 list”还是“返回单个字符串”。",
        "deliverable": "function",
        "expected_model": "stateful_ops", 
        "ambiguity_check": "present"
    }
]

def create_task():
    try:
        resp = requests.post(f"{BASE_URL}/oracle/task", json={"project_id": "r5_fix_test"}, headers=HEADERS)
        if resp.status_code != 200:
             return None
        return resp.json().get("task_id")
    except Exception as e:
        print(f"Error creating task: {e}")
        return None

def get_db_row(version_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT version_id, status, interaction_model_pred, llm_provider_used, 
                   llm_model_used, spec_llm_request_id, llm_latency_ms, attempts, 
                   schema_version, spec_prompt_version, missing_fields_json, 
                   attempt_fail_reasons_json
            FROM oracle_task_versions WHERE version_id = ?
        """, (version_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            d = dict(row)
            return d
        return None
    except Exception as e:
        print(f"DB Error: {e}")
        return None

def log(msg):
    print(msg)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_regression():
    # Clear file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("")

    summary_table = []

    for t in TASKS:
        task_id = create_task()
        if not task_id:
            log(f"Failed to create task for {t['id']}")
            continue
            
        req_body = {
            "task_description": t["desc"],
            "deliverable_type": t["deliverable"],
            "language": "python",
            "runtime": "python"
        }
        
        # Analyze
        try:
            resp = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=req_body, headers=HEADERS)
            analyze_json = resp.json()
        except Exception as e:
            analyze_json = {"error": str(e)}

        version_id = analyze_json.get("version_id")
        
        # Get Version
        ver_json = {}
        if version_id:
            try:
                v_resp = requests.get(f"{BASE_URL}/oracle/version/{version_id}")
                ver_json = v_resp.json()
            except:
                pass
        
        # Get Debug
        debug_json = {}
        try:
            d_resp = requests.get(f"{BASE_URL}/oracle/debug/last_spec_call")
            debug_json = d_resp.json()
        except:
            pass

        # Get DB Row
        db_row = {}
        if version_id:
            db_row = get_db_row(version_id)

        # Print Block
        log(f"\n--- EVIDENCE BLOCK {t['id']} ---")
        log(f"1) Case ID: {t['id']}")
        log("2) UI settings used (exact):")
        log(f"   - deliverable={t['deliverable']}")
        log("   - language=python")
        log("   - runtime=python")
        
        log("3) Exact Analyze request body (JSON):")
        log(json.dumps(req_body, indent=2, ensure_ascii=False))
        
        log("4) Analyze response JSON (FULL):")
        log(json.dumps(analyze_json, indent=2, ensure_ascii=False))
        
        log("5) GET /oracle/version/{version_id} JSON (FULL):")
        log(json.dumps(ver_json, indent=2, ensure_ascii=False))
        
        log("6) GET /oracle/debug/last_spec_call JSON (FULL, immediately after):")
        log(json.dumps(debug_json, indent=2, ensure_ascii=False))
        
        # Evaluation
        inter_pred = debug_json.get("interaction_model_pred", "N/A")
        ambiguities = ver_json.get("ambiguities", [])
        
        spec_summary = ver_json.get("spec_summary", {})
        signature = spec_summary.get("signature", {})
        returns_val = signature.get("returns", "N/A") if signature else "N/A"

        # Check assertions
        inter_ok = "yes"
        if t["expected_model"] != "any" and inter_pred != t["expected_model"]:
            inter_ok = f"no (expected {t['expected_model']}, got {inter_pred})"
            
        amb_ok = "yes"
        if t["ambiguity_check"] == "empty" and len(ambiguities) > 0:
            amb_ok = "no (expected empty)"
        elif t["ambiguity_check"] == "present" and len(ambiguities) == 0:
            amb_ok = "no (expected present)"
            
        conf_ok = "yes" if ver_json.get("oracle_confidence", 0) > 0 else "no"
        
        returns_ok = "yes" if returns_val == "Any" or "Union" in str(returns_val) else f"no (got {returns_val})"

        log("7) One-line evaluation results:")
        log(f"   - interaction_model_match={inter_ok}")
        log(f"   - ambiguity_check={amb_ok}")
        log(f"   - confidence_reasonable={conf_ok}")
        log(f"   - returns_type_check={returns_ok}")
        
        log("8) EVIDENCE_BLOCK_COMPLETE=true")

        # DB Proof Section
        log(f"\n--- DB ROW PROOF {t['id']} ---")
        if db_row:
            # Format row nicely for display
            log(json.dumps(db_row, indent=2, ensure_ascii=False))
        else:
            log("DB ROW NOT FOUND")

        # Collect summary data
        req_ids = debug_json.get("request_ids", [])
        req_prefix = req_ids[0][:6] if req_ids else "None"
        
        persistence_ok = "yes" if db_row and db_row.get("spec_llm_request_id") else "no"

        summary_table.append({
            "case_id": t["id"],
            "version_id": version_id,
            "status": ver_json.get("status", "error"),
            "interaction_model_pred": inter_pred,
            "ambiguities_count": len(ambiguities),
            "oracle_confidence": ver_json.get("oracle_confidence", 0),
            "attempts": debug_json.get("attempts", 0),
            "llm_latency_ms": debug_json.get("latency_ms", 0),
            "llm_model_used": debug_json.get("model", "N/A"),
            "spec_llm_request_id_prefix": req_prefix,
            "persistence_ok": persistence_ok,
            "returns_val": returns_val,
            "notes": "OK" if inter_ok=="yes" and amb_ok=="yes" and returns_ok=="yes" else "FAIL"
        })
        
        time.sleep(1)

    log("\n============================================================")
    log("FINAL SUMMARY TABLE (MUST)")
    log("============================================================")
    log("case_id | version_id | status | interaction_model_pred | ambiguities_count | oracle_confidence | attempts | llm_latency_ms | llm_model_used | spec_llm_request_id_prefix | persistence_ok | returns_val | notes")
    
    for row in summary_table:
        log(f"{row['case_id']} | {row['version_id']} | {row['status']} | {row['interaction_model_pred']} | {row['ambiguities_count']} | {row['oracle_confidence']} | {row['attempts']} | {row['llm_latency_ms']} | {row['llm_model_used']} | {row['spec_llm_request_id_prefix']} | {row['persistence_ok']} | {row['returns_val']} | {row['notes']}")

if __name__ == "__main__":
    run_regression()
