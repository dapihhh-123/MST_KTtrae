
import unittest
from unittest.mock import patch
from backend.services.oracle.llm_oracle import generate_spec_with_llm
from backend.services.oracle.types import TaskSpec

class TestSpecDrift(unittest.TestCase):
    
    @patch('backend.services.oracle.llm_oracle.llm_service.chat')
    def test_deliverable_drift_correction(self, mock_chat):
        """
        Test that if LLM returns 'cli' for a 'script' request, it is corrected.
        """
        # Mock LLM returning 'cli' even though we asked for 'script'
        bad_llm_json = {
            "goal_one_liner": "Do something",
            "interaction_model": "cli_stdio",
            "deliverable": "cli",  # DRIFT!
            "language": "python",
            "runtime": "python",
            "signature": { "function_name": "main", "args": [], "returns": "int" },
            "constraints": [],
            "assumptions": [],
            "output_shape": {"type": "file"},
            "ambiguities": [],
            "public_examples": [],
            "confidence_reasons": ["Reason 1"]
        }
        
        mock_chat.return_value = {
            "text": "```json\n" + str(bad_llm_json).replace("'", '"') + "\n```",
            "model": "gpt-4o",
            "latency_ms": 100,
            "request_id": "req_drift"
        }
        
        spec_dict, meta = generate_spec_with_llm(
            task_description="Run a script",
            language="python",
            runtime="python",
            deliverable_type="script", # Requesting script
            retries=1
        )
        
        # Assertion: The deliverable in the result MUST be 'script'
        self.assertEqual(spec_dict["deliverable"], "script", "Deliverable type should be corrected to 'script'")
        
        # Check if confidence reasons are passed through
        self.assertEqual(spec_dict.get("confidence_reasons"), ["Reason 1"])

if __name__ == '__main__':
    unittest.main()
