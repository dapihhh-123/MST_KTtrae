
import json
import logging
from typing import Dict, Any, List, Optional
from backend.services.llm_service import llm_service

logger = logging.getLogger("Backend")

def generate_spec(
    task_description: str,
    language: str,
    runtime: str,
    deliverable_type: str,
    optional_interface_constraints: Optional[Dict[str, Any]] = None,
    optional_nonfunctional_constraints: Optional[Dict[str, Any]] = None,
    debug_invalid_mock: bool = False
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    
    prompt = f"""
You are a Senior Technical Analyst. Analyze the User Task and produce a formal Specification JSON.

User Task:
{task_description}

Context:
- Deliverable: {deliverable_type}
- Language: {language}
- Runtime: {runtime}

Requirements:
1. goal_one_liner: Concise summary.
2. signature: Function name, args list, return type.
3. constraints: List HARD rules.
4. assumptions: List defaults.
5. output_ops: List operations that produce output.
6. output_shape: Schema of the answer (MUST be a JSON Object, e.g. {{"type": "boolean"}} or {{"id": "int"}}).
7. ambiguities: List specific ambiguities. Format: [{{ "ambiguity_id": "str", "question": "str", "choices": [...] }}].
8. public_examples: List 3 examples. Format: [{{ "name": "str", "input": "...", "expected": "..." }}].

Output Format:
Return ONLY raw JSON.
"""

    messages = [{"role": "system", "content": "You are a precise system architect."}, {"role": "user", "content": prompt}]
    
    try:
        resp = llm_service.chat(messages, temperature=0.1)
        text = resp["text"]
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        data = json.loads(text.strip())
        
        # Sanitize data
        if not isinstance(data.get("output_shape"), dict):
            data["output_shape"] = {"type": str(data.get("output_shape", "unknown"))}
            
        if not isinstance(data.get("ambiguities"), list):
            data["ambiguities"] = []
        else:
            valid_amb = []
            for a in data["ambiguities"]:
                if isinstance(a, dict):
                    # Sanitize choices
                    choices = a.get("choices", [])
                    if isinstance(choices, list):
                        valid_choices = []
                        for c in choices:
                            if isinstance(c, dict): valid_choices.append(c)
                            elif isinstance(c, str): valid_choices.append({"choice_id": c, "text": c})
                        a["choices"] = valid_choices
                    else:
                        a["choices"] = []
                    valid_amb.append(a)
            data["ambiguities"] = valid_amb
        
        # Sanitize public_examples
        pe = data.get("public_examples", [])
        if isinstance(pe, list):
            valid_pe = []
            for item in pe:
                if isinstance(item, dict):
                    # Ensure name is string
                    if not isinstance(item.get("name"), str):
                         item["name"] = "Example"
                    # Ensure input/expected exist
                    if "input" not in item: item["input"] = {}
                    if "expected" not in item: item["expected"] = "result"
                    valid_pe.append(item)
            data["public_examples"] = valid_pe
        else:
            data["public_examples"] = []

        # Sanitize signature
        sig = data.get("signature")
        if isinstance(sig, dict):
            if "function_name" not in sig: sig["function_name"] = "solve"
            if "args" not in sig: sig["args"] = []
            if "returns" not in sig: sig["returns"] = "Any"
            # Ensure args is list of strings
            if isinstance(sig["args"], list):
                new_args = []
                for a in sig["args"]:
                    if isinstance(a, str): new_args.append(a)
                    elif isinstance(a, dict): new_args.append(a.get("name", "arg"))
                    else: new_args.append(str(a))
                sig["args"] = new_args
            else:
                sig["args"] = []
        
        # Ensure mandatory fields
        data["deliverable"] = deliverable_type
        data["language"] = language
        data["runtime"] = runtime
        if "output_ops" not in data: data["output_ops"] = []
        if "constraints" not in data: data["constraints"] = []
        if "assumptions" not in data: data["assumptions"] = []
        
        metadata = {
            "raw_text": resp["text"],
            "model": "mock_llm_v1" if "text" in resp else "unknown", # In real LLM service this would be better
            "provider": "mock",
            "latency_ms": 0, # Mock doesn't track this yet
            "prompt_version": "v1.0"
        }
        return data, metadata

    except Exception as e:
        logger.error(f"Spec Generation Failed: {e}")
        # Return a valid fallback
        fallback = {
            "goal_one_liner": f"Error generating spec: {str(e)}",
            "deliverable": deliverable_type,
            "language": language,
            "runtime": runtime,
            "signature": {"function_name": "solve", "args": [], "returns": "Any"},
            "ambiguities": [],
            "constraints": [],
            "assumptions": [],
            "output_ops": [],
            "output_shape": {},
            "public_examples": []
        }
        return fallback, {"error": str(e)}

def generate_tests(
    spec_json: Dict[str, Any],
    confirmations: Dict[str, Any],
    public_examples_count: int,
    hidden_tests_count: int,
    difficulty_profile: Optional[Dict[str, Any]],
    seed: int,
    debug_invalid_mock: bool
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    
    # Mock tests if spec failed
    if "Error generating spec" in spec_json.get("goal_one_liner", ""):
        return {
            "public_examples": [],
            "hidden_tests": []
        }, {}

    prompt = f"""
Generate Test Cases for the following Spec.
Spec: {json.dumps(spec_json, indent=2)}
Requirements:
1. Generate {public_examples_count} public examples.
2. Generate {hidden_tests_count} hidden tests.
Output JSON:
{{
  "public_examples": [ {{ "name": "...", "input": {{...}}, "expected": ... }} ],
  "hidden_tests": [ {{ "name": "...", "input": {{...}}, "expected": ... }} ]
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        resp = llm_service.chat(messages, temperature=0.3)
        text = resp["text"]
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        data = json.loads(text.strip())
        metadata = {
            "raw_text": resp["text"],
            "model": "mock_llm_v1",
            "provider": "mock",
            "prompt_version": "v1.0"
        }
        return data, metadata
    except Exception as e:
        logger.error(f"Test Generation Failed: {e}")
        return {
            "public_examples": spec_json.get("public_examples", []),
            "hidden_tests": []
        }, {"error": str(e)}
