
from typing import Dict, Any, List, Set, Optional, Tuple
import re

class SpecValidationError(Exception):
    def __init__(self, error_code: str, field_path: str, message: str, raw_snippet: str = ""):
        self.error_code = error_code
        self.field_path = field_path
        self.message = message
        self.raw_snippet = raw_snippet
        super().__init__(f"[{error_code}] {field_path}: {message}")

TRIGGERS = [
    (r"返回\s*(list|列表)\s*还是\s*(字符串|string)", "output_format"),
    (r"输出格式不明确", "output_format"),
    (r"并列怎么办", "tie_breaking"),
    (r"任意一个", "tie_breaking"),
    (r"遇到不存在\s*id", "error_handling"),
    (r"可能是\s*list\s*也可能是\s*string", "input_format"),
    (r"大小写敏感", "case_sensitivity"),
    (r"返回单个值还是列表", "return_type_conflict")
]

def trigger_scan(task_description: str) -> Set[str]:
    found = set()
    desc_lower = task_description.lower()
    for pattern, category in TRIGGERS:
        if re.search(pattern, task_description, re.IGNORECASE): # Regex search on raw string
            found.add(category)
    return found

def validate_and_normalize(spec_dict: Dict[str, Any], task_description: str) -> Dict[str, Any]:
    # 2.1 Required top-level fields
    required_fields = ["goal_one_liner", "deliverable", "language", "runtime", "signature", "ambiguities", "public_examples"]
    for field in required_fields:
        if field not in spec_dict:
             raise SpecValidationError("spec_invalid", field, "Missing required field")
        
        # Basic type checks
        val = spec_dict[field]
        if field == "goal_one_liner" and (not isinstance(val, str) or not val.strip()):
            raise SpecValidationError("spec_invalid", field, "Must be non-empty string")
        if field == "deliverable" and val not in ["cli", "function", "script"]:
            raise SpecValidationError("spec_invalid", field, "Must be 'cli', 'function', or 'script'")
        if field == "ambiguities" and not isinstance(val, list):
            raise SpecValidationError("spec_invalid", field, "Must be a list")
        if field == "public_examples" and not isinstance(val, list):
            raise SpecValidationError("spec_invalid", field, "Must be a list")

    sig = spec_dict["signature"]
    if not isinstance(sig, dict):
        raise SpecValidationError("spec_invalid", "signature", "Must be a dict")
    
    if "function_name" not in sig or not isinstance(sig["function_name"], str) or not sig["function_name"]:
        raise SpecValidationError("spec_invalid", "signature.function_name", "Must be non-empty string")
    if "args" not in sig or not isinstance(sig["args"], list):
        raise SpecValidationError("spec_invalid", "signature.args", "Must be a list of strings")
    if "returns" not in sig or not isinstance(sig["returns"], str) or not sig["returns"]:
        raise SpecValidationError("spec_invalid", "signature.returns", "Must be non-empty string")

    # 2.2 Deliverable-specific shape
    deliverable = spec_dict["deliverable"]
    fname = sig["function_name"]
    args = sig["args"]
    constraints = spec_dict.get("constraints", []) or []
    
    if deliverable == "cli":
        if fname != "main":
             raise SpecValidationError("spec_invalid", "signature.function_name", "CLI deliverable must have function_name='main'")
        if args != []:
             raise SpecValidationError("spec_invalid", "signature.args", "CLI deliverable must have args=[]")

    if deliverable == "script":
        if args != []:
             raise SpecValidationError("spec_invalid", "signature.args", "SCRIPT deliverable must have args=[]")

    if deliverable == "function":
        if fname == "main":
             raise SpecValidationError("spec_invalid", "signature.function_name", "Function deliverable must not be 'main'")

    # 3. Ambiguity Detection
    detected_triggers = trigger_scan(task_description)
    if detected_triggers:
        ambiguities = spec_dict["ambiguities"]
        # Check if ambiguities cover the triggers
        # Heuristic: check if ambiguity_id or question contains keywords related to trigger category
        # Simple mapping for now
        keywords_map = {
            "output_format": ["output", "format", "return", "list", "string"],
            "tie_breaking": ["tie", "break", "order", "sort"],
            "error_handling": ["error", "id", "missing", "invalid"],
            "input_format": ["input", "list", "string", "format"],
            "case_sensitivity": ["case", "sensitive", "ignore"],
            "return_type_conflict": ["return", "type", "list", "string"]
        }
        
        for category in detected_triggers:
            covered = False
            keywords = keywords_map.get(category, [])
            for amb in ambiguities:
                aid = str(amb.get("ambiguity_id", "")).lower()
                q = str(amb.get("question", "")).lower()
                if any(k in aid for k in keywords) or any(k in q for k in keywords):
                    covered = True
                    break
            
            if not covered:
                raise SpecValidationError("spec_missing_ambiguity", "ambiguities", f"Missing ambiguity for detected trigger: {category}")

    # 4. Returns vs Examples
    ret = sig["returns"]
    examples = spec_dict["public_examples"]
    
    def guess_kind(val):
        if isinstance(val, int): return "int"
        if isinstance(val, str): return "str"
        if isinstance(val, list): return "list"
        if isinstance(val, dict): return "dict"
        return "unknown"

    # Only check strict types if return type is not Any/Union
    if ret in ["int", "str", "list", "dict"]:
        for ex in examples:
            expected = ex.get("expected")
            kind = guess_kind(expected)
            if kind != "unknown" and ret != kind:
                # Relaxed list check: list vs list[int]
                if ret == "list" and kind == "list": continue
                if ret == "dict" and kind == "dict": continue
                
                raise SpecValidationError("spec_example_mismatch", "public_examples", f"Return type {ret} contradicts example type {kind}")

    # 4.2 Ambiguity implies wide returns
    has_output_ambiguity = False
    for amb in spec_dict["ambiguities"]:
        q = (amb.get("question") or "").lower()
        aid = (amb.get("ambiguity_id") or "").lower()
        keywords = ["return", "output", "format", "shape", "list vs string", "single string"]
        if any(k in q or k in aid for k in keywords):
            has_output_ambiguity = True
            break
    
    if has_output_ambiguity:
        if ret not in ["Any", "Union"] and "Union" not in ret:
             raise SpecValidationError("spec_invalid", "signature.returns", "Ambiguous output format requires Any or Union return type")

    # 5. Normalization
    # Canonicalize constraints
    if "constraints" in spec_dict:
        spec_dict["constraints"] = [c.strip() for c in spec_dict["constraints"] if c.strip()]
    
    # Trim goal
    spec_dict["goal_one_liner"] = spec_dict["goal_one_liner"].strip()
    
    # Ensure unique ambiguity IDs
    amb_ids = set()
    for amb in spec_dict["ambiguities"]:
        aid = amb.get("ambiguity_id", "ambiguity")
        original_aid = aid
        counter = 2
        while aid in amb_ids:
            aid = f"{original_aid}_{counter}"
            counter += 1
        amb["ambiguity_id"] = aid
        amb_ids.add(aid)

    return spec_dict
