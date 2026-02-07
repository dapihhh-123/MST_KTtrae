
import requests
import argparse
import sys
import json
import sqlite3

BASE_URL = "http://127.0.0.1:8001/api/oracle"
DB_PATH = "backend.db"

def safe_json_load(text):
    if not text: return None
    try:
        return json.loads(text)
    except:
        return None

def replay_analyze(version_id):
    print(f"Replaying Analyze for Version ID: {version_id}")
    
    # Check DB for raw data
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM oracle_task_versions WHERE version_id = ?", (version_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print("Version not found in DB.")
        return

    row = dict(row)
    
    print("\n[DB Trace Record]")
    print(f"Version ID: {row.get('version_id')}")
    print(f"Status: {row.get('status')}")
    print(f"Model Used: {row.get('llm_model_used')}")
    print(f"Provider: {row.get('llm_provider_used')}")
    print(f"Prompt Version: {row.get('spec_prompt_version')}")
    
    raw_spec = row.get("spec_llm_raw_json")
    if raw_spec:
        print("\n[Raw LLM Output Found]")
        print(f"Length: {len(raw_spec)} chars")
        print(f"Snippet: {raw_spec[:100]}...")
    else:
        print("\n[!] Raw LLM Output MISSING in DB")
        
    print("\n[Replay Verification]")
    # Since we can't exactly replay without the input description (which is missing from DB as noted),
    # we will verify the schema validity of the stored raw output if present.
    
    if raw_spec:
        try:
            # Assume raw_spec might be markdown wrapped
            text = raw_spec
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            data = json.loads(text.strip())
            print("[PASS] Raw output is valid JSON (after extraction).")
            
            # Check required fields
            req = ["goal_one_liner", "deliverable"]
            missing = [k for k in req if k not in data]
            if missing:
                print(f"[FAIL] Raw JSON missing keys: {missing}")
            else:
                print("[PASS] Raw JSON contains minimal keys.")
                
        except Exception as e:
            print(f"[FAIL] Raw output parsing failed: {e}")
    else:
        print("[SKIP] Cannot verify raw output (missing).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version_id", required=True)
    args = parser.parse_args()
    
    replay_analyze(args.version_id)
