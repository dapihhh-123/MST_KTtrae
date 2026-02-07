import requests
import json
import time

BASE_URL = "http://localhost:8001/api"
HEADERS = {"Content-Type": "application/json"}

def print_section(title, content):
    print(f"\n({title})")
    if isinstance(content, (dict, list)):
        print(json.dumps(content, indent=2))
    else:
        print(content)

def main():
    print("Starting verification...")

    # (2) GET /oracle/debug/config JSON
    try:
        resp = requests.get(f"{BASE_URL}/oracle/debug/config")
        print_section("2", resp.json())
    except Exception as e:
        print(f"Error getting config: {e}")

    # Create a task to work with
    try:
        task_resp = requests.post(f"{BASE_URL}/oracle/task", json={"project_id": "test_proj"}, headers=HEADERS)
        if task_resp.status_code != 200:
             print(f"Error creating task: {task_resp.text}")
             return
        task_id = task_resp.json()["task_id"]
        print(f"Created Task ID: {task_id}")
    except Exception as e:
        print(f"Error creating task: {e}")
        return

    # (3) Two Analyze calls
    
    # Call A: Well-specified CLI task
    print("\n--- Call A: Well-specified CLI task ---")
    body_a = {
        "task_description": "Create a CLI tool that takes two numbers as arguments and prints their sum.",
        "deliverable_type": "cli",
        "language": "python",
        "runtime": "python"
    }
    try:
        resp_a = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=body_a, headers=HEADERS)
        print("Response A Status:", resp_a.status_code)
        try:
            print_section("3A Response", resp_a.json())
        except:
            print("Response A text:", resp_a.text)
    except Exception as e:
        print(f"Error Call A: {e}")
        
    # Get last spec call A
    try:
        debug_a = requests.get(f"{BASE_URL}/oracle/debug/last_spec_call")
        print_section("3A Debug Last Call", debug_a.json())
    except Exception as e:
        print(f"Error Debug A: {e}")

    # Call B: Underspecified task
    print("\n--- Call B: Underspecified task ---")
    body_b = {
        "task_description": "Process the data.", # Very vague
        "deliverable_type": "function",
        "language": "python",
        "runtime": "python"
    }
    try:
        resp_b = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=body_b, headers=HEADERS)
        print("Response B Status:", resp_b.status_code)
        try:
            print_section("3B Response", resp_b.json())
        except:
            print("Response B text:", resp_b.text)
    except Exception as e:
        print(f"Error Call B: {e}")

    # Get last spec call B
    try:
        debug_b = requests.get(f"{BASE_URL}/oracle/debug/last_spec_call")
        print_section("3B Debug Last Call", debug_b.json())
    except Exception as e:
        print(f"Error Debug B: {e}")

    # (4) DB Queries hint
    print("\n(4) DB Queries (Run these manually or via python script if you have DB access):")
    print("SELECT version_id,status,llm_provider_used,llm_model_used,spec_llm_request_id,attempts,llm_latency_ms,missing_fields_json,attempt_fail_reasons_json FROM oracle_task_versions ORDER BY created_at DESC LIMIT 2;")
    
    # We can also execute it here if we use sqlite3 directly
    import sqlite3
    try:
        conn = sqlite3.connect("backend.db")
        cursor = conn.cursor()
        cursor.execute("SELECT version_id,status,llm_provider_used,llm_model_used,spec_llm_request_id,attempts,llm_latency_ms,missing_fields_json,attempt_fail_reasons_json FROM oracle_task_versions ORDER BY created_at DESC LIMIT 2")
        rows = cursor.fetchall()
        print_section("4 DB Results", rows)
        conn.close()
    except Exception as e:
        print(f"Error querying DB: {e}")

if __name__ == "__main__":
    main()
