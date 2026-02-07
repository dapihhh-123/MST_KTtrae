import unittest

from backend.services.oracle.spec_validator import validate_and_normalize


class TestScriptSpecValidator(unittest.TestCase):
    def test_script_allows_non_main_function_name(self):
        spec = {
            "goal_one_liner": "Clean receipt file",
            "deliverable": "script",
            "language": "python",
            "runtime": "python",
            "signature": {"function_name": "entrypoint", "args": [], "returns": "None"},
            "constraints": [],
            "assumptions": [],
            "output_ops": [],
            "output_shape": {"type": "files"},
            "ambiguities": [],
            "public_examples": [],
        }
        normalized = validate_and_normalize(spec, "write a script")
        self.assertEqual(normalized["deliverable"], "script")

    def test_script_rejects_nonempty_args(self):
        spec = {
            "goal_one_liner": "Clean receipt file",
            "deliverable": "script",
            "language": "python",
            "runtime": "python",
            "signature": {"function_name": "entrypoint", "args": ["x"], "returns": "None"},
            "constraints": [],
            "assumptions": [],
            "output_ops": [],
            "output_shape": {"type": "files"},
            "ambiguities": [],
            "public_examples": [],
        }
        with self.assertRaises(Exception) as ctx:
            validate_and_normalize(spec, "write a script")
        self.assertIn("SCRIPT deliverable must have args=[]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

