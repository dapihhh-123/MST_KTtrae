import openai
from backend.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL, LLM_TIMEOUT_SECONDS
from typing import Generator, Optional, List, Dict, Any
import logging
import time
import json
import os

logger = logging.getLogger("Backend")

class LLMService:
    def __init__(self):
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY is not set. LLM features will fail.")
            self.client = None
        else:
            self.client = openai.OpenAI(
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
                timeout=LLM_TIMEOUT_SECONDS
            )

    def chat(self, messages: List[Dict[str, str]], 
             model: str = OPENAI_MODEL, 
             temperature: float = 0.7, 
             max_tokens: Optional[int] = None,
             tools: Optional[List[Dict]] = None,
             tool_choice: Optional[Any] = None,
             extra_client_config: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Unified chat method with error handling and standard response format.
        extra_client_config: Optional dict with 'api_key' and 'base_url' to override default client.
        """
        # 1. Check for Offline/Mock Mode
        if os.getenv("ORACLE_MOCK_MODE") == "true":
            user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
            return self._mock_response(user_msg, model)

        client_to_use = self.client
        if extra_client_config:
            # Temporary client for this request (e.g. ZhipuAI)
            try:
                client_to_use = openai.OpenAI(
                    api_key=extra_client_config.get("api_key"),
                    base_url=extra_client_config.get("base_url"),
                    timeout=LLM_TIMEOUT_SECONDS
                )
            except Exception as e:
                logger.error(f"Failed to create extra client: {e}")
                raise

        if not client_to_use:
            raise RuntimeError("LLM client not initialized (missing API key).")
        
        # Bypass for test key (Simulation Mode)
        # if self.client.api_key.startswith("sk-proj-test"):
        #     user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        #     return self._mock_response(user_msg, model)

        start_time = time.time()
        # Prepare kwargs, filtering None values
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        # Use with_raw_response to capture headers (x-request-id)
        # Assuming openai>=1.0
        try:
            raw_response = client_to_use.chat.completions.with_raw_response.create(**kwargs)
            response = raw_response.parse()
            # extract x-request-id
            req_id = raw_response.headers.get("x-request-id")
        except AttributeError:
            # Fallback for older versions or mocks
            response = client_to_use.chat.completions.create(**kwargs)
            req_id = None

        # Extract content
        message = response.choices[0].message
        content = message.content
        
        # Usage
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        } if response.usage else {}
        
        return {
            "text": content,
            "raw": response,
            "usage": usage,
            "latency_ms": int((time.time() - start_time) * 1000),
            "request_id": req_id or response.id # Fallback to completion ID only if header missing, but prefer header
        }

    def _mock_response(self, user_msg: str, model: str) -> Dict[str, Any]:
        content = "{}"
        lc = user_msg.lower()
        
        # --- B1 Clear Tasks ---
        if "mock_clear_cli" in lc:
             content = json.dumps({
                 "goal_one_liner": "Clear CLI Task",
                 "interaction_model": "cli_stdio",
                 "deliverable": "cli",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "main", "args": [], "returns": "Any" },
                 "constraints": ["Read from stdin, print to stdout"],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {},
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": "in", "expected": "out"}]
             })
        elif "mock_clear_func" in lc:
             content = json.dumps({
                 "goal_one_liner": "Clear Function Task",
                 "interaction_model": "function_single",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "solve", "args": ["x"], "returns": "int" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {"type": "int"},
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": [1], "expected": 2}]
             })
        elif "mock_clear_ops" in lc:
             content = json.dumps({
                 "goal_one_liner": "Clear Ops Task",
                 "interaction_model": "stateful_ops",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "solve", "args": ["ops"], "returns": "List[str]" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": ["add", "list"],
                 "output_shape": {"type": "list"},
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": [["add", "x"]], "expected": []}]
             })
        
        # --- B2 Ambiguous Task ---
        elif "mock_ambiguous" in lc:
             content = json.dumps({
                 "goal_one_liner": "Ambiguous Task",
                 "interaction_model": "function_single",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "solve", "args": ["x"], "returns": "Any" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {"type": "any"},
                 "ambiguities": [{"ambiguity_id": "amb1", "question": "Q1?", "choices": [{"choice_id": "a", "text": "A"}]}],
                 "public_examples": [{"name": "ex1", "input": [1], "expected": 1}]
             })

        # --- E1 Error Injection ---
        elif "trigger_json_fail" in lc:
            # First attempt returns bad json, subsequent fixed? 
            # Actually, _mock_response is stateless unless we track it.
            # But the 'repair' logic appends new messages.
            if "return only a valid json" in lc or "json parse error" in lc:
                # This is the repair attempt
                content = json.dumps({
                    "goal_one_liner": "Repaired JSON",
                    "deliverable": "function",
                    "language": "python",
                    "runtime": "python",
                    "signature": {"function_name": "f", "args": [], "returns": "int"},
                    "ambiguities": [], "constraints": [], "assumptions": [], "output_ops": [], "output_shape": {}, "public_examples": []
                })
            else:
                # Initial failure
                content = "This is not JSON."

        elif "trigger_type_mismatch" in lc:
             # Returns int, example expects str
             # If repair hint present, fix it?
             if "fix signature.returns" in lc:
                 ret_type = "str"
             else:
                 ret_type = "int"
                 
             content = json.dumps({
                 "goal_one_liner": "Type Mismatch Task",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "solve", "args": [], "returns": ret_type },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {},
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": [], "expected": "string_val"}]
             })
             
        # --- Legacy Mocks (Keep them) ---
        elif "ticketing system" in lc: # OPS_001
             content = json.dumps({
                 "goal_one_liner": "Ticket system with CRUD operations",
                 "interaction_model": "stateful_ops",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "solve", "args": ["ops"], "returns": "List[str]" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": ["create", "update", "delete", "status"],
                 "output_shape": { "type": "list" },
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": [], "expected": []}]
             })
        elif "cli tool that reads" in lc: # CLI_001
             content = json.dumps({
                 "goal_one_liner": "Sum numbers from stdin",
                 "interaction_model": "cli_stdio",
                 "deliverable": "cli",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "main", "args": [], "returns": "int" },
                 "constraints": ["Read from stdin, print to stdout"],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {},
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": "1\\n2", "expected": "3"}]
             })
        elif "filter_large_numbers" in lc: # DATA_001
             content = json.dumps({
                 "goal_one_liner": "Filter numbers > 100",
                 "interaction_model": "function_single",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "filter_large_numbers", "args": ["data"], "returns": "List[int]" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {"type": "list[int]"},
                 "ambiguities": [],
                 "public_examples": [{"name": "ex1", "input": [101, 10], "expected": [101]}]
             })
        elif "cache" in lc and "get(k)" in lc: # MIX_001
             content = json.dumps({
                 "goal_one_liner": "LRU Cache implementation",
                 "interaction_model": "stateful_ops",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "solve", "args": ["ops"], "returns": "List[str]" },
                 "constraints": ["O(1) complexity"],
                 "assumptions": [],
                 "output_ops": ["get", "set"],
                 "output_shape": { "type": "list" },
                 "ambiguities": [],
                 "public_examples": []
             })
        elif "process the user list" in lc: # AMB_001
             content = json.dumps({
                 "goal_one_liner": "Process user list",
                 "interaction_model": "function_single",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "process_users", "args": ["users"], "returns": "Any" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {"type": "any"},
                 "ambiguities": [{"ambiguity_id": "perf_metric", "question": "What performance metric?", "choices": [{"choice_id": "cpu", "text": "CPU"}, {"choice_id": "mem", "text": "Memory"}]}],
                 "public_examples": []
             })
        elif "list of operations [add, sub]" in lc: # OPS_005 (Confusable 1 -> function_single)
             content = json.dumps({
                 "goal_one_liner": "Calculate single result from ops",
                 "interaction_model": "function_single",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "calculate", "args": ["ops"], "returns": "int" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {"type": "int"},
                 "ambiguities": [],
                 "public_examples": []
             })
        elif "parses command line arguments string" in lc: # CLI_005 (Confusable 2 -> function_single)
             content = json.dumps({
                 "goal_one_liner": "Parse CLI args string",
                 "interaction_model": "function_single",
                 "deliverable": "function",
                 "language": "python",
                 "runtime": "python",
                 "signature": { "function_name": "parse_args", "args": ["arg_str"], "returns": "Dict" },
                 "constraints": [],
                 "assumptions": [],
                 "output_ops": [],
                 "output_shape": {"type": "dict"},
                 "ambiguities": [],
                 "public_examples": []
             })
             
        elif "summarize_logs" in lc: # LOGS_001
             # FIX: Ensure consistent logic for modules and invalid lines
             content = json.dumps({
                 "public_examples": [
                     {
                         "name": "Basic case with mixed logs",
                         "input": [[
                             "t1 | INFO | m1",
                             "t2 | ERROR | m1",
                             "t3 | DEBUG | m2", # Ignored level
                             "t4 | INFO | m1",
                             "   ",             # Empty line (ignored)
                             "invalid line"     # Invalid
                         ], 2],
                         "expected": "Processed 3 lines, kept 1 errors, invalid: 1, modules: {'m1': 3}"
                     }
                 ],
                 "hidden_tests": [
                     {
                         "name": "More errors than last_n_errors",
                         "input": [[
                             "t1 | ERROR | m1",
                             "t2 | ERROR | m1",
                             "t3 | ERROR | m2",
                             "t4 | INFO | m1"
                         ], 2],
                         # Fixed: m1 count includes INFO line (total 3), m2 is 1
                         "expected": "Processed 4 lines, kept 2 errors, invalid: 0, modules: {'m1': 3, 'm2': 1}"
                     },
                     {
                         "name": "Mixed valid and invalid lines",
                         "input": [[
                             "just text",       # Invalid
                             "t1 | INFO | m1",  # Valid
                             "   ",             # Empty (Strip -> Empty, Ignored)
                             "t2 | WARN | m2",  # Valid
                             ""                 # Empty (Ignored)
                         ], 1],
                         # Fixed: invalid count should only be 1 ("just text"). "   " is empty.
                         "expected": "Processed 2 lines, kept 0 errors, invalid: 1, modules: {'m1': 1, 'm2': 1}"
                     }
                 ]
             })
             
        return {
            "text": content,
            "raw": None,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "latency_ms": 350
        }

    def generate_hint(self, context: str, model: str = OPENAI_MODEL) -> str:
        """
        Legacy wrapper for simple hint generation.
        """
        messages = [
            {"role": "system", "content": "You are a helpful coding tutor."},
            {"role": "user", "content": context}
        ]
        try:
            result = self.chat(messages, model=model)
            return result["text"]
        except Exception as e:
            return f"Error generating hint: {str(e)}"

    def stream_completion(self, messages: list, model: str = OPENAI_MODEL) -> Generator[str, None, None]:
        """
        Streaming generation for 'AI typing' effect.
        """
        if not self.client:
            yield "LLM service unavailable."
            return

        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM Stream Error: {e}")
            yield f"[Error: {e}]"

llm_service = LLMService()
