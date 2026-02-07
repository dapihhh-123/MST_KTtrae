
import unittest
from unittest.mock import patch, MagicMock
import json
import sqlite3
import requests
import time
from backend.services.oracle.llm_oracle import generate_spec_with_llm, OracleAnalyzeError
from backend.routers.oracle import create_spec, SpecBody
from backend.database import get_db, SessionLocal

# DB Path for verification
DB_PATH = "backend.db"

class TestValidatorRegression(unittest.TestCase):
    
    def setUp(self):
        self.db = SessionLocal()
        
    def tearDown(self):
        self.db.close()

    def get_db_row(self, version_id):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM oracle_task_versions WHERE version_id = ?", (version_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @patch('backend.services.oracle.llm_oracle.llm_service.chat')
    def test_negative_cases(self, mock_chat):
        # 1. Missing required field (spec_invalid)
        bad_json_1 = {
            "goal_one_liner": "Missing signature",
            "deliverable": "function",
            "language": "python",
            "runtime": "python",
            # Missing signature
            "ambiguities": [],
            "public_examples": [],
            "constraints": [],
            "assumptions": []
        }
        
        # 2. Ambiguity trigger present but no ambiguity (spec_missing_ambiguity)
        desc_2 = "输出格式不明确，返回 list 还是 string？"
        bad_json_2 = {
            "goal_one_liner": "Ambiguity ignored",
            "deliverable": "function",
            "language": "python",
            "runtime": "python",
            "signature": {"function_name": "solve", "args": [], "returns": "Any"},
            "ambiguities": [], # Empty!
            "public_examples": [],
            "constraints": [],
            "assumptions": []
        }

        # 3. Return type mismatch (spec_example_mismatch)
        bad_json_3 = {
            "goal_one_liner": "Mismatch types",
            "deliverable": "function",
            "language": "python",
            "runtime": "python",
            "signature": {"function_name": "solve", "args": [], "returns": "int"},
            "ambiguities": [],
            "public_examples": [{"name": "ex1", "input": "", "expected": "I am a string"}], # Mismatch
            "constraints": [],
            "assumptions": []
        }

        scenarios = [
            ("N1", "Missing Field", "Generic task", bad_json_1, "spec_invalid"),
            ("N2", "Missing Ambiguity", desc_2, bad_json_2, "spec_missing_ambiguity"),
            ("N3", "Example Mismatch", "Generic task", bad_json_3, "spec_example_mismatch"),
        ]

        print("\n=== NEGATIVE TESTS EXECUTION ===")
        
        for case_id, name, desc, json_data, expected_error in scenarios:
            print(f"\nRunning {case_id}: {name}")
            
            # Mock LLM to return the bad JSON every time (so retries fail)
            mock_chat.return_value = {
                "text": json.dumps(json_data),
                "model": "mock-gpt-4o",
                "latency_ms": 123,
                "request_id": f"req_{case_id}"
            }
            
            # We call the router function logic directly or simulate it?
            # Calling generate_spec_with_llm directly raises exception.
            # Calling create_spec router function handles persistence.
            # I will call create_spec but I need to mock DB dependency or use real DB.
            # I'll use real DB via 'db' session.
            
            # Create Task first
            task_id = f"task_{case_id}_{int(time.time())}"
            # Insert task manually to DB to satisfy FK
            # But create_spec calls _get_task which queries DB.
            # I'll create a task via API logic or raw SQL.
            from backend import models
            t = models.OracleTask(task_id=task_id, project_id="test")
            self.db.add(t)
            self.db.commit()

            # Prepare body
            body = SpecBody(
                task_description=desc,
                deliverable_type="function",
                language="python",
                runtime="python"
            )
            
            # Call create_spec
            # It expects HTTPException on failure.
            from fastapi import HTTPException
            
            version_id = None
            try:
                create_spec(task_id, body, self.db)
            except HTTPException as e:
                # Check 422
                if e.status_code == 422:
                    detail = e.detail
                    if isinstance(detail, dict):
                        version_id = detail.get("version_id")
                        fail_reasons = detail.get("fail_reasons", [])
                        print(f"Caught expected HTTPException 422. Version: {version_id}")
                        # Verify error type in fail reasons
                        found_error = False
                        for f in fail_reasons:
                            if expected_error in f["message"]:
                                found_error = True
                                break
                        if found_error:
                            print(f"SUCCESS: Found expected error '{expected_error}' in fail reasons.")
                        else:
                            print(f"FAILURE: Expected '{expected_error}' but got: {fail_reasons}")
                    else:
                        print(f"FAILURE: Detail is not dict: {detail}")
                else:
                    print(f"FAILURE: Unexpected status code {e.status_code}")
            except Exception as e:
                print(f"FAILURE: Unexpected exception: {e}")

            # DB Proof
            if version_id:
                row = self.get_db_row(version_id)
                print(f"--- EVIDENCE BLOCK {case_id} ---")
                print(f"Failure Type: {expected_error}")
                print("Debug Info (Last Call):")
                print(json.dumps({
                    "status": row["status"],
                    "attempts": row["attempts"],
                    "fail_reasons": row["attempt_fail_reasons_json"]
                }, indent=2))
                print("DB ROW PROOF:")
                print(json.dumps(row, indent=2, default=str))
            else:
                print("No version_id created, cannot show DB proof.")

if __name__ == '__main__':
    unittest.main()
