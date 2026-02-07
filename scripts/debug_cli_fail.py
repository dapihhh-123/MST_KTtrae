import requests
import json

BASE_URL = "http://localhost:8001/api"

def debug():
    # Create Task
    resp = requests.post(f"{BASE_URL}/oracle/task", json={"project_id": "debug"})
    task_id = resp.json()["task_id"]
    
    # Analyze
    body = {
        "task_description": "mock_clear_cli",
        "deliverable_type": "cli",
        "language": "python",
        "runtime": "python"
    }
    resp = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=body)
    print(f"Status: {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2))
    except:
        print(resp.text)

if __name__ == "__main__":
    debug()
