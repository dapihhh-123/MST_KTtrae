import unittest
from unittest.mock import patch

from backend.services.oracle.llm_oracle import generate_spec_with_llm


class TestReceiptScriptNoRetry(unittest.TestCase):
    @patch("backend.services.oracle.llm_oracle.llm_service.chat")
    def test_receipt_script_passes_on_first_attempt(self, mock_chat):
        receipt_desc = """写一个 Python 脚本 clean_receipt.py：

读取同目录 receipt.txt，每行可能像：
- 苹果 x2  7.50
- BANANA*1 3.2
- 牛奶 1  12

解析出 name、qty、price（price 单位元，允许整数或小数；qty 为正整数）。
输出 cleaned.csv（UTF-8），表头：name,qty,price,total
其中 total=qty*price，price 和 total 都保留两位小数。

无法解析的非空行写入 invalid_lines.txt（原样保存）。
空行忽略。

最后在控制台打印：success_lines、invalid_lines、grand_total（两位小数）。"""

        llm_json = {
            "goal_one_liner": "Clean receipt lines into CSV",
            "interaction_model": "script_file",
            "deliverable": "script",
            "language": "python",
            "runtime": "python",
            "signature": {"function_name": "entrypoint", "args": [], "returns": "None"},
            "constraints": [
                "Read input from ./receipt.txt",
                "Write cleaned rows to ./cleaned.csv (UTF-8) with header name,qty,price,total",
                "Write unparseable non-empty lines to ./invalid_lines.txt (keep original line)",
                "Ignore empty lines",
                "price and total formatted to 2 decimal places",
            ],
            "assumptions": [
                "price is the last number on the line",
                "qty is parsed from x<integer> or *<integer>; otherwise the line is invalid",
            ],
            "output_ops": [],
            "output_shape": {"type": "files"},
            "ambiguities": [],
            "public_examples": [],
            "confidence_reasons": ["Fixed file names and CSV header"],
        }

        mock_chat.return_value = {
            "text": "```json\n" + str(llm_json).replace("'", '"') + "\n```",
            "model": "gpt-4o",
            "latency_ms": 10,
            "request_id": "req_receipt",
        }

        spec, meta = generate_spec_with_llm(
            task_description=receipt_desc,
            language="python",
            runtime="python",
            deliverable_type="script",
            retries=2,
        )

        self.assertEqual(meta.get("attempts"), 1)
        self.assertEqual(spec.get("deliverable"), "script")


if __name__ == "__main__":
    unittest.main()

