
import unittest
from unittest.mock import patch, MagicMock
from backend.services.oracle.llm_oracle import generate_spec_with_llm, OracleAnalyzeError

class TestCliSpecFix(unittest.TestCase):
    
    def setUp(self):
        self.cli_task_desc = "Create a CLI tool that renames files based on a pattern. Input: --pattern and --target."
    
    @patch('backend.services.oracle.llm_oracle.llm_service.chat')
    def test_cli_spec_no_stdin_constraint(self, mock_chat):
        """
        Test that a CLI spec WITHOUT 'Read from stdin' is accepted (Validator relaxed).
        """
        # Mock LLM response: CLI spec using argparse (no stdin constraint)
        cli_json = {
            "goal_one_liner": "Rename files via CLI",
            "interaction_model": "cli_stdio",
            "deliverable": "cli",
            "language": "python",
            "runtime": "python",
            "signature": { 
                "function_name": "main", 
                "args": [], 
                "returns": "int" 
            },
            "ambiguities": [],
            "public_examples": [ 
                { 
                    "name": "ex1", 
                    "input": ["--pattern", "*.txt"], 
                    "expected": 0
                } 
            ],
            "constraints": [
                "Use argparse for arguments",
                "Print to stdout"
            ],
            "assumptions": [],
            "output_ops": [],
            "output_shape": {"type": "str"}
        }

        mock_chat.return_value = {
            "text": "```json\n" + str(cli_json).replace("'", '"') + "\n```",
            "model": "gpt-4o",
            "latency_ms": 100,
            "request_id": "req_cli_fix"
        }
        
        try:
            spec, meta = generate_spec_with_llm(
                task_description=self.cli_task_desc,
                language="python",
                runtime="python",
                deliverable_type="cli",
                retries=1
            )
            
            # Assertions
            constraints = spec.get("constraints", [])
            print(f"DEBUG: constraints={constraints}")
            
            # 1. Ensure "Read from stdin" is NOT present (as per our mock)
            has_stdin = any("read from stdin" in c.lower() for c in constraints)
            self.assertFalse(has_stdin, "Should not have 'Read from stdin' constraint")
            
            # 2. Ensure "Print to stdout" IS present (as per our mock)
            has_stdout = any("print to stdout" in c.lower() for c in constraints)
            self.assertTrue(has_stdout, "Should have 'Print to stdout' constraint")
            
            # 3. Ensure no validation errors occurred (attempts == 1)
            self.assertEqual(meta["attempts"], 1, "Should succeed on first attempt without validation error")
            
        except OracleAnalyzeError as e:
            self.fail(f"Analysis failed unexpectedly: {e}")

    @patch('backend.services.oracle.llm_oracle.llm_service.chat')
    def test_cli_spec_with_explicit_stdin(self, mock_chat):
        """
        Test that a CLI spec WITH 'Read from stdin' is ALSO accepted (Backward compatibility).
        """
        cli_json_stdin = {
            "goal_one_liner": "Process pipe input",
            "interaction_model": "cli_stdio",
            "deliverable": "cli",
            "language": "python",
            "runtime": "python",
            "signature": { "function_name": "main", "args": [], "returns": "int" },
            "ambiguities": [],
            "public_examples": [],
            "constraints": [
                "Read from stdin, print to stdout"
            ],
            "assumptions": [],
            "output_shape": {"type": "str"}
        }

        mock_chat.return_value = {
            "text": "```json\n" + str(cli_json_stdin).replace("'", '"') + "\n```",
            "model": "gpt-4o",
            "latency_ms": 100,
            "request_id": "req_cli_stdin"
        }

        try:
            spec, meta = generate_spec_with_llm(
                task_description="Read from pipe",
                language="python",
                runtime="python",
                deliverable_type="cli",
                retries=1
            )
            constraints = spec.get("constraints", [])
            has_stdin = any("read from stdin" in c.lower() for c in constraints)
            self.assertTrue(has_stdin, "Should preserve 'Read from stdin' if present")
            self.assertEqual(meta["attempts"], 1)

        except OracleAnalyzeError as e:
            self.fail(f"Analysis failed unexpectedly: {e}")

if __name__ == '__main__':
    unittest.main()
