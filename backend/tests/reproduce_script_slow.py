
import unittest
from unittest.mock import patch
from backend.services.oracle.llm_oracle import generate_spec_with_llm, OracleAnalyzeError
import time

class TestScriptSlow(unittest.TestCase):
    
    def setUp(self):
        self.script_task_desc = """
        写一个 Python 脚本 clean_receipt.py：
        读取同目录 receipt.txt，每行可能像：
        - 苹果 x2  7.50
        - BANANA*1 3.2
        解析出 name、qty、price。
        输出 cleaned.csv。
        """
    
    @patch('backend.services.oracle.llm_oracle.llm_service.chat')
    def test_script_generation_retry_loop(self, mock_chat):
        """
        Test that deliverable_type='script' causes retries because validator rejects it.
        """
        # Mock LLM response: Correct JSON structure but deliverable="script"
        script_json = {
            "goal_one_liner": "Clean receipt data",
            "interaction_model": "cli_stdio",
            "deliverable": "script",  # This is what LLM generates based on prompt
            "language": "python",
            "runtime": "python",
            "signature": { 
                "function_name": "main", 
                "args": [], 
                "returns": "int" 
            },
            "ambiguities": [],
            "public_examples": [],
            "constraints": ["Print to stdout"],
            "assumptions": [],
            "output_shape": {"type": "file"}
        }

        # We simulate that LLM keeps returning "script" because the prompt asks for it
        mock_chat.return_value = {
            "text": "```json\n" + str(script_json).replace("'", '"') + "\n```",
            "model": "gpt-4o",
            "latency_ms": 100,
            "request_id": "req_script_1"
        }
        
        start_time = time.time()
        try:
            # retries=2 means total 3 attempts
            spec, meta = generate_spec_with_llm(
                task_description=self.script_task_desc,
                language="python",
                runtime="python",
                deliverable_type="script",
                retries=2 
            )
            # If it succeeds, we check attempts
            print(f"Attempts used: {meta['attempts']}")
            
        except OracleAnalyzeError as e:
            print(f"\nCaught expected error: {e}")
            print(f"Metadata attempts: {e.metadata['attempts']}")
            print(f"Fail reasons: {e.metadata['attempt_fail_reasons']}")
            
            # Assert that the failure is due to deliverable validation
            self.assertTrue(any("Must be 'cli' or 'function'" in r for r in e.metadata['attempt_fail_reasons']))

if __name__ == '__main__':
    unittest.main()
