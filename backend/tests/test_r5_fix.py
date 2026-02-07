
import unittest
from unittest.mock import patch, MagicMock
from backend.services.oracle.llm_oracle import generate_spec_with_llm, OracleAnalyzeError

class TestR5Fix(unittest.TestCase):
    
    def setUp(self):
        self.r5_task_desc = """ops 可能既是 list 格式，也可能是字符串命令（例如 `"ADD 1 hello"`）。你需要决定是否支持两种格式，或者只支持一种并写 assumptions。
另外：输出要求不明确，请你生成歧义让用户选择“返回 list”还是“返回单个字符串”。"""
    
    @patch('backend.services.oracle.llm_oracle.llm_service.chat')
    def test_r5_return_type_ambiguity_is_non_contradictory(self, mock_chat):
        # Mock LLM response: Bad response (contradiction)
        bad_json = {
            "goal_one_liner": "Process operations",
            "interaction_model": "stateful_ops",
            "deliverable": "function",
            "language": "python",
            "runtime": "python",
            "signature": { 
                "function_name": "solve", 
                "args": ["ops"], 
                "returns": "str" 
            },
            "ambiguities": [ 
                { 
                    "ambiguity_id": "output_format", 
                    "question": "What should be the output format? Return list or string?", 
                    "choices": [
                        {"choice_id": "list", "text": "Return list"},
                        {"choice_id": "string", "text": "Return string"}
                    ] 
                } 
            ],
            "public_examples": [ 
                { 
                    "name": "ex1", 
                    "input": ["ADD 1"], 
                    "expected": ["Added 1"] 
                } 
            ],
            "constraints": [],
            "assumptions": [],
            "output_ops": ["ADD"],
            "output_shape": {"type": "list"}
        }

        # Good response (Corrected)
        good_json = bad_json.copy()
        good_json["signature"] = { 
            "function_name": "solve", 
            "args": ["ops"], 
            "returns": "Union[list, str]" 
        }

        # Side effect: First call returns bad (triggering validation), second returns good
        mock_chat.side_effect = [
            {
                "text": "```json\n" + str(bad_json).replace("'", '"').replace("True", "true").replace("False", "false") + "\n```",
                "model": "gpt-4o",
                "latency_ms": 100,
                "request_id": "req_bad"
            },
            {
                "text": "```json\n" + str(good_json).replace("'", '"').replace("True", "true").replace("False", "false") + "\n```",
                "model": "gpt-4o",
                "latency_ms": 100,
                "request_id": "req_good"
            }
        ]
        
        try:
            # We allow 1 retry
            spec, meta = generate_spec_with_llm(
                task_description=self.r5_task_desc,
                language="python",
                runtime="python",
                deliverable_type="function",
                retries=1
            )
            
            # Assertions (Success Criteria)
            # 1. Check signature.returns
            returns_type = spec.get("signature", {}).get("returns", "")
            self.assertTrue(
                returns_type == "Any" or "Union" in returns_type, 
                f"signature.returns should be Any/Union, got {returns_type}"
            )
            
            # 2. Verify that we actually retried (attempts should be 2)
            self.assertEqual(meta["attempts"], 2, "Should have retried due to validation error")
            
        except OracleAnalyzeError as e:
            self.fail(f"Analysis failed unexpectedly: {e}")

if __name__ == '__main__':
    unittest.main()
