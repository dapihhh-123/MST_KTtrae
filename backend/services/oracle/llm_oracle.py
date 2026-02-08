
import json
import logging
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from pydantic import ValidationError
from backend.services.llm_service import llm_service
from backend.services.oracle.types import TaskSpec
from backend.services.oracle.spec_validator import validate_and_normalize, SpecValidationError
from backend.config import OPENAI_MODEL, ZHIPU_API_KEY

logger = logging.getLogger("Backend")

# --- ZhipuAI Configuration ---
ZHIPU_MODEL = "glm-4.7" # Latest Flagship Model
zhipu_config = {
    "api_key": ZHIPU_API_KEY,
    "base_url": "https://open.bigmodel.cn/api/paas/v4/"
}
# -----------------------------

class OracleAnalyzeError(Exception):
    def __init__(self, message: str, metadata: Dict[str, Any]):
        super().__init__(message)
        self.metadata = metadata

PROMPT_VERSION = "v2.1-real"
SCHEMA_VERSION = "v1.0"

def compute_input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def validate_required_fields(spec: TaskSpec, interaction_model: str) -> List[str]:
    missing = []
    # D1. Required Fields Validator
    
    # Universal
    if not spec.goal_one_liner: missing.append("goal_one_liner")
    if not spec.deliverable: missing.append("deliverable")
    
    # Per Interaction Model
    if interaction_model == "stateful_ops" or spec.deliverable == "function":
        if not spec.signature:
            missing.append("signature")
        else:
            if not spec.signature.function_name: missing.append("signature.function_name")
            if spec.signature.args is None: missing.append("signature.args")
        
        if not spec.output_shape: missing.append("output_shape")
        
        if interaction_model == "stateful_ops":
            if not spec.output_ops: missing.append("output_ops")
    
    elif interaction_model == "cli_stdio" or spec.deliverable == "cli":
        if not spec.signature: missing.append("signature") # Usually 'main'
        # Check constraints for stdin/stdout mention? (Lightweight check)
        
    return missing

def detect_contradictions(spec: TaskSpec, raw_desc: str) -> List[str]:
    contradictions = []
    # E1. Contradiction Checks
    desc_lower = raw_desc.lower()
    
    # Example: output_ops vs constraints
    if spec.output_ops and "only return" in desc_lower and "sequence" not in desc_lower:
        # Weak heuristic, but illustrative
        pass

    # DEBUG
    print(f"DEBUG: Checking contradictions. Returns={spec.signature.returns if spec.signature else 'None'}")
    if spec.ambiguities:
        print(f"DEBUG: Ambiguities found: {len(spec.ambiguities)}")

    # V1 — Return type must not contradict examples
    if spec.public_examples and spec.signature:
        ret = spec.signature.returns or ""
        # Only check concrete types
        if ret not in ["Any", "Union", "unknown"] and "Union" not in ret:
            for ex in spec.public_examples:
                ex_kind = "unknown"
                if isinstance(ex.expected, list): ex_kind = "list"
                elif isinstance(ex.expected, str): ex_kind = "str"
                elif isinstance(ex.expected, bool): ex_kind = "bool"
                elif isinstance(ex.expected, int): ex_kind = "int"
                elif isinstance(ex.expected, dict): ex_kind = "dict"
                
                # Check for mismatch
                if ret != ex_kind and ex_kind != "unknown":
                    contradictions.append(f"return_type_conflict: signature.returns={ret} examples_kind={ex_kind}")
                    break

    # V2 — If ambiguity includes output/return decision, signature.returns must be broad
    if spec.ambiguities and spec.signature:
        ret = spec.signature.returns or ""
        is_broad = ret == "Any" or "Union" in ret
        if not is_broad:
            for amb in spec.ambiguities:
                # TaskSpec uses List[Dict[str, Any]] for ambiguities
                amb_id = str(amb.get("ambiguity_id") or "")
                q = str(amb.get("question") or "").lower()
                
                keywords = ["return", "output", "format", "shape", "list vs string", "single string"]
                if any(k in amb_id.lower() for k in keywords) or any(k in q for k in keywords):
                    contradictions.append(f"ambiguous_return_type_requires_broad_signature: signature.returns={ret}")
                    break

    # V3 — If ambiguity exists, assumptions must not “decide the ambiguity”
    # (Skipping V3 as it's complex and V1/V2 cover the main R5 issue)
        
    return contradictions

import time
import openai

import re

def repair_json_syntax(text: str) -> str:
    """
    Attempts to repair common Python-to-JSON syntax errors in LLM output.
    """
    # 1. Convert Python tuples (1, 2) -> [1, 2]
    # This regex looks for parens containing numbers, strings, or other parens
    # It is recursive-ish but simple regex can handle 1 level deep.
    # Let's target the specific failure case: lists of tuples [(1,2), (3,4)]
    
    # Replace (1, 2) with [1, 2] inside list context
    # Strategy: Replace all (d, d) with [d, d] first
    text = re.sub(r'\(\s*([-\d\.]+)\s*,\s*([-\d\.]+)\s*\)', r'[\1, \2]', text)
    
    # 2. Python literals
    text = re.sub(r':\s*None\b', ': null', text)
    text = re.sub(r':\s*True\b', ': true', text)
    text = re.sub(r':\s*False\b', ': false', text)
    
    # 3. Trailing commas in lists/objects (common in Python)
    text = re.sub(r',\s*([\]}])', r'\1', text)
    
    return text

def generate_spec_with_llm(
    task_description: str,
    language: str,
    runtime: str,
    deliverable_type: str,
    retries: int = 2
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    
    # 1. Input Normalization (A1)
    normalized_desc = task_description.strip()
    input_hash = compute_input_hash(normalized_desc)
    
    system_prompt = f"""Role: Technical Architect. Analyze user task -> Implementation Spec (JSON).
    
    Context:
    - Deliverable: {deliverable_type}
    - Language: {language}
    - Runtime: {runtime}
    
    Output Schema (Strict JSON):
    {{
        "goal_one_liner": "str",
        "interaction_model": "function_single|stateful_ops|cli_stdio",
        "deliverable": "{deliverable_type}",
        "language": "{language}",
        "runtime": "{runtime}",
        "signature": {{ "function_name": "str", "args": ["str"], "returns": "str" }},
        "constraints": ["str"],
        "assumptions": ["str"],
        "output_ops": ["str (only for stateful_ops)"],
        "output_shape": {{ "type": "str", ... }},
        "ambiguities": [ {{ "ambiguity_id": "str", "question": "str", "choices": [ {{ "choice_id": "str", "text": "str" }} ] }} ],
        "public_examples": [ {{ "name": "str", "input": any, "expected": any }} ],
        "confidence_reasons": ["str"]
    }}
    
    Interaction Models:
    1. "stateful_ops": Sequence tasks (e.g. create/delete/query).
       - signature.function_name="solve", args=["ops"]
       - Fill "output_ops" & "output_shape"
    2. "function_single": Pure calculation (e.g. is_prime).
       - Define exact function_name & args
    3. "cli_stdio": Command Line Interface.
       - signature.function_name="main", args=[], returns="int"
       - Input: Default to argparse (command line arguments). ONLY add "Read from stdin" constraint if user explicitly requests stdin/pipe input.
       - Output: Print to stdout (and/or stderr).
       - Add constraint: "Print to stdout" (unless stderr is primarily used).
    4. "script_file": Independent Script (deliverable="script").
       - signature.function_name="entrypoint", args=[], returns="void"
       - Logic: Reads specific files, writes specific files. NO exit code return needed.

    Rules:
    1. "constraints": MUST capture explicit rules (input format, sorting, edge cases).
       - For delimited input (e.g. "A|B|C"), MUST specify: "Split by '|' with max splits = N-1 (preserve delimiter in last part)."
       - For case sensitivity: DEFAULT to "Exact match (case-sensitive)" unless user says "case-insensitive".
       - For dictionary output: MUST specify exact keys (e.g. "Output dict must have keys: 'id', 'count'").
       - For parsing (e.g. "Milk 1 12.5"): DO NOT use loose heuristics like "extract all numbers". MUST specify exact format: "qty is the integer after 'x' or '*'; price is the last number". If format is ambiguous (e.g. no markers), create an AMBIGUITY instead of guessing.
    2. "public_examples": Valid JSON only (use null/true/false, no tuples).
    3. Missing info -> Add to "ambiguities".
    4. Do NOT invent constraints. Use "assumptions" for defaults ONLY if standard practice.
    5. "confidence_reasons": List 1-3 reasons why this spec is accurate (e.g. "Fixed input format", "Standard output", "Clear edge cases").
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": normalized_desc}
    ]
    
    attempts = 0
    fail_reasons = []
    last_fail_reason: Optional[str] = None
    
    # Defaults for metadata in case of catastrophic failure
    last_request_id = None
    last_latency_ms = 0
    
    while attempts <= retries:
        attempts += 1
        t0 = time.time()
        try:
            # A1. Real LLM Call
            response = llm_service.chat(
                messages=messages,
                model=ZHIPU_MODEL, # Use Zhipu model
                temperature=0.2,
                extra_client_config=zhipu_config, # Inject Zhipu config
                response_format={"type": "json_object"}
            )
            
            last_latency_ms = response.get("latency_ms")
            last_request_id = response.get("request_id")
            
            raw_text = response["text"]
            # Extract JSON if markdown wrapped
            json_text = raw_text
            if "```json" in raw_text:
                json_text = raw_text.split("```json")[1].split("```")[0]
            elif "```" in raw_text:
                json_text = raw_text.split("```")[1].split("```")[0]
            
            try:
                data = json.loads(json_text.strip())
            except json.JSONDecodeError:
                repaired_json_text = repair_json_syntax(json_text)
                data = json.loads(repaired_json_text.strip())
            
            spec = TaskSpec.model_validate(data)
            if spec.deliverable != deliverable_type:
                logger.info(f"Correcting deliverable_type drift: {spec.deliverable} -> {deliverable_type}")
                spec.deliverable = deliverable_type
                data["deliverable"] = deliverable_type

            if deliverable_type == "script":
                sig = data.get("signature") or {}
                if isinstance(sig, dict) and sig.get("returns") == "int":
                    sig["returns"] = "Any"

            # C2. Advanced Validation & Normalization
            try:
                data = validate_and_normalize(data, normalized_desc)
                # Re-validate against Pydantic to ensure normalization didn't break schema
                spec = TaskSpec.model_validate(data)
            except SpecValidationError as e:
                # FALLBACK STRATEGY (Option 2) for SpecValidationError (e.g. Example Mismatch)
                if attempts > retries and e.error_code == "spec_example_mismatch":
                    logger.warning(f"Final attempt failed with SpecValidationError: {e.message}. Applying fallback strategy.")
                    
                    # Force resolution: Widen return type to Any
                    spec.signature.returns = "Any"
                    
                    # Add ambiguity record
                    spec.ambiguities.append({
                        "ambiguity_id": "auto_resolved_example_mismatch",
                        "question": f"Type mismatch detected in final attempt: {e.message}. Resolved by widening return type.",
                        "choices": [{"choice_id": "any", "text": "Return Any (Fallback)"}]
                    })
                    
                    metadata = {
                        "normalized_input_hash": input_hash,
                        "prompt_version": PROMPT_VERSION,
                        "schema_version": SCHEMA_VERSION,
                        "interaction_model_pred": interaction_model,
                        "attempts": attempts,
                        "attempt_fail_reasons": fail_reasons + [f"spec_validation_fallback: {e.message}"],
                        "llm_provider_used": "zhipu",
                        "llm_model_used": response.get("model", ZHIPU_MODEL),
                        "llm_latency_ms": last_latency_ms,
                        "request_id": last_request_id,
                        "raw_text": raw_text,
                        "missing_fields": missing,
                        "ambiguities": spec.ambiguities
                    }
                    return spec.model_dump(), metadata

                # Stop retrying blindly: Check if this error is identical to the previous one
                current_fail_reason = f"{e.error_code}: {e.message} (field: {e.field_path})"
                if last_fail_reason == current_fail_reason:
                    metadata = {
                        "normalized_input_hash": input_hash,
                        "prompt_version": PROMPT_VERSION,
                        "schema_version": SCHEMA_VERSION,
                        "interaction_model_pred": interaction_model,
                        "attempts": attempts,
                        "attempt_fail_reasons": fail_reasons + [f"{current_fail_reason} [STUCK]"],
                        "llm_provider_used": "zhipu",
                        "llm_model_used": response.get("model", ZHIPU_MODEL),
                        "llm_latency_ms": last_latency_ms,
                        "request_id": last_request_id,
                        "raw_text": raw_text,
                        "missing_fields": missing,
                        "ambiguities": spec.ambiguities
                    }
                    raise OracleAnalyzeError("analyze_failed_stuck_validation", metadata)
                
                fail_reasons.append(current_fail_reason)
                last_fail_reason = current_fail_reason
                
                # Inject validator feedback into subsequent LLM attempts
                # OPTIMIZATION: Provide only a concise error summary to avoid token explosion
                # Construct Fix Guidance
                guidance = f"""Validation Error: {e.message}
Rule ID: {e.error_code}
Field: {e.field_path}
Instruction: Please fix the JSON to comply with this rule. Do not repeat the same invalid pattern."""
                
                messages.append({"role": "user", "content": guidance})
                continue

            # D1. Required Fields Validator
            interaction_model = data.get("interaction_model", "unknown")
            missing = validate_required_fields(spec, interaction_model)
            
            if missing:
                # Self-Correction Loop
                fail_reasons.append(f"missing_fields: {missing}")
                messages.append({"role": "user", "content": f"Validation Error: Missing required fields {missing}. Please fix."})
                continue
                
            # E1. Contradictions
            contradictions = detect_contradictions(spec, normalized_desc)
            if contradictions:
                # FALLBACK STRATEGY (Option 2): If this is the final attempt, degrade to low_confidence instead of failing.
                if attempts > retries:
                    logger.warning(f"Final attempt failed with contradictions: {contradictions}. Applying fallback strategy.")
                    
                    # Force resolution: Widen return type to Any
                    spec.signature.returns = "Any"
                    
                    # Add ambiguity record
                    spec.ambiguities.append({
                        "ambiguity_id": "auto_resolved_contradiction",
                        "question": f"Contradiction detected in final attempt: {contradictions[0]}. Resolved by widening return type.",
                        "choices": [{"choice_id": "any", "text": "Return Any (Fallback)"}]
                    })
                    
                    # Return success with fallback metadata
                    metadata = {
                        "normalized_input_hash": input_hash,
                        "prompt_version": PROMPT_VERSION,
                        "schema_version": SCHEMA_VERSION,
                        "interaction_model_pred": interaction_model,
                        "attempts": attempts,
                        "attempt_fail_reasons": fail_reasons + [f"contradictions_fallback: {contradictions}"],
                        "llm_provider_used": "zhipu",
                        "llm_model_used": response.get("model", ZHIPU_MODEL),
                        "llm_latency_ms": last_latency_ms,
                        "request_id": last_request_id,
                        "raw_text": raw_text,
                        "missing_fields": missing,
                        "ambiguities": spec.ambiguities
                    }
                    # We must dump the modified spec, not the original data
                    return spec.model_dump(), metadata

                fail_reasons.append(f"contradictions: {contradictions}")
                messages.append({"role": "user", "content": f"Validation Error: Contradictions detected {contradictions}. \n\nCRITICAL FIX REQUIRED:\n1. If the task is a CLI tool printing text, change 'signature.returns' to 'Any' or 'str'.\n2. If the examples use strings/lists, ensure 'signature.returns' matches.\n3. Do not assume 'int' for CLI unless it only returns an exit code.\n\nPlease fix the JSON."})
                continue
            
            # Success
            metadata = {
                "normalized_input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "interaction_model_pred": interaction_model,
                "attempts": attempts,
                "attempt_fail_reasons": fail_reasons,
                "llm_provider_used": "zhipu", # Enforced by usage of llm_service with OPENAI_API_KEY
                "llm_model_used": response.get("model", ZHIPU_MODEL),
                "llm_latency_ms": last_latency_ms,
                "request_id": last_request_id,
                "raw_text": raw_text,
                "missing_fields": missing, # Should be empty or acceptable
                "ambiguities": data.get("ambiguities", [])
            }
            
            return data, metadata
            
        except ValidationError as e:
            err_msg = str(e)
            
            # FALLBACK STRATEGY (Option 2) for Type Mismatches
            if attempts > retries and ("contradicts example type" in err_msg or "type mismatch" in err_msg):
                logger.warning(f"Final attempt failed with validation error: {err_msg}. Applying fallback strategy.")
                
                # Force resolution: Widen return type to Any
                spec.signature.returns = "Any"
                
                # Add ambiguity record
                spec.ambiguities.append({
                    "ambiguity_id": "auto_resolved_type_mismatch",
                    "question": f"Type mismatch detected in final attempt: {err_msg}. Resolved by widening return type.",
                    "choices": [{"choice_id": "any", "text": "Return Any (Fallback)"}]
                })
                
                metadata = {
                    "normalized_input_hash": input_hash,
                    "prompt_version": PROMPT_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "interaction_model_pred": interaction_model,
                    "attempts": attempts,
                    "attempt_fail_reasons": fail_reasons + [f"validation_fallback: {err_msg}"],
                    "llm_provider_used": "zhipu",
                    "llm_model_used": response.get("model", ZHIPU_MODEL),
                    "llm_latency_ms": last_latency_ms,
                    "request_id": last_request_id,
                    "raw_text": raw_text,
                    "missing_fields": missing,
                    "ambiguities": spec.ambiguities
                }
                return spec.model_dump(), metadata

            fail_reasons.append(f"schema_fail: {err_msg}")
            # Retry logic
            if attempts <= retries:
                messages.append({"role": "user", "content": f"JSON Schema Validation Failed: {err_msg}. Please correct the JSON format. If there is a type conflict, set 'returns' to 'Any'."})
        except json.JSONDecodeError:
            fail_reasons.append("json_parse_fail")
            if attempts <= retries:
                messages.append({"role": "user", "content": "JSON Parse Error: The output was not valid JSON. Please return ONLY a valid JSON object matching the schema v1.0. Do not include any markdown formatting or extra text."})
            elif attempts > retries:
                # GRACEFUL DEGRADATION
                logger.error("JSON parse failed after retries. Returning fallback spec.")
                fallback_spec = {
                    "goal_one_liner": "Automatic analysis failed due to parse error. Please edit spec manually.",
                    "deliverable": deliverable_type,
                    "language": language,
                    "runtime": runtime,
                    "signature": {"function_name": "solve", "args": [], "returns": "Any"},
                    "constraints": [],
                    "assumptions": [],
                    "ambiguities": [{
                        "ambiguity_id": "parse_fail",
                        "question": "The system could not parse the AI response. Please review the spec manually.",
                        "choices": [{"choice_id": "ok", "text": "OK"}]
                    }],
                    "public_examples": []
                }
                meta = {
                    "normalized_input_hash": input_hash,
                    "attempts": attempts,
                    "attempt_fail_reasons": fail_reasons + ["final_parse_fail"],
                    "llm_provider_used": "zhipu",
                    "llm_model_used": ZHIPU_MODEL,
                    "raw_text": locals().get("raw_text", ""),
                    "request_id": last_request_id
                }
                return fallback_spec, meta
        except Exception as e:
            last_latency_ms = int((time.time() - t0) * 1000)
            if hasattr(e, 'request_id'):
                last_request_id = e.request_id
            fail_reasons.append(f"llm_error: {str(e)}")
            # If it's a provider error, maybe don't retry? But we will retry for now.
            
    # Fallback if all retries failed - STOP FAKE SUCCESS
    metadata = {
        "normalized_input_hash": input_hash,
        "attempts": attempts,
        "attempt_fail_reasons": fail_reasons,
        "final_status": "analyze_failed",
        "raw_text": locals().get("raw_text", ""),
        "request_id": last_request_id,
        "llm_latency_ms": last_latency_ms,
        "llm_provider_used": "zhipu",
        "llm_model_used": ZHIPU_MODEL,
        "missing_fields": [], # Can't know if we failed before validation
        "ambiguities": []
    }
    raise OracleAnalyzeError("analyze_failed_after_retries", metadata)

def generate_tests_with_llm(
    spec_json: Dict[str, Any],
    confirmations: Dict[str, Any],
    public_examples_count: int,
    hidden_tests_count: int,
    difficulty_profile: Optional[Dict[str, Any]],
    seed: int
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    
    prompt = f"""Generate Test Cases.
    Spec: {json.dumps(spec_json)}
    Count: {public_examples_count} public, {hidden_tests_count} hidden.
    
    Output JSON Schema:
    {{
      "public_examples": [ {{ "name": "str", "input": ["args..."], "expected": any }} ],
      "hidden_tests": [ {{ "name": "str", "input": ["args..."], "expected": any }} ]
    }}
    IMPORTANT Rules:
    1. 'name' is MANDATORY.
    2. 'input' MUST be the list of arguments passed to the function.
       - Example: func(a, b) -> input: [a, b]
       - Example: func(L) -> input: [[1, 2]] (Argument is a list, so wrap it)
    """
    
    try:
        response = llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            model=ZHIPU_MODEL, # Use Zhipu
            extra_client_config=zhipu_config # Use Zhipu config
        )
        # ... parsing logic similar to above ...
        raw = response["text"]
        if "```json" in raw: raw = raw.split("```json")[1].split("```")[0]
        data = json.loads(raw.strip())
        
        meta = {
            "llm_provider_used": "zhipu",
            "llm_model_used": response.get("model", ZHIPU_MODEL),
            "raw_text": response["text"]
        }
        return data, meta
    except Exception as e:
        return {"public_examples": [], "hidden_tests": []}, {"error": str(e)}
