from typing import Dict, Any, List, Optional
import json

class PedagogicalClassifier:
    def classify(self, 
                 err_type_coarse: str, 
                 error_message: str, 
                 diff_summary: Dict[str, Any],
                 tests_summary: Optional[str] = None
                 ) -> Dict[str, Any]:
        
        result = {}
        # 1. Compile Error Path
        if err_type_coarse == "COMPILE" or err_type_coarse == "CompileErr":
            result = self._classify_compile(error_message)
            
        # 2. Logic Error Path
        elif err_type_coarse == "LOGIC" or err_type_coarse == "LogicFail":
            result = self._classify_logic(tests_summary, diff_summary)
            
        # 3. Default/Correct
        else:
            result = {
                "err_type_pedagogical": "UNKNOWN",
                "natural_language": "No specific error detected, but proceeding with caution.",
                "recommendations": ["Review recent changes.", "Run tests to ensure stability."],
                "confidence": 0.3,
                "rule_id": None
            }
            
        # Enrich with Bridging Fields
        return self._add_bridging_fields(result)

    def _classify_compile(self, error_message: str) -> Dict[str, Any]:
        msg = error_message.lower() if error_message else ""
        
        # RECALL: NameError, Import, NotDefined
        if any(x in msg for x in ["nameerror", "not defined", "import", "module"]):
            return {
                "err_type_pedagogical": "RECALL",
                "natural_language": "It seems like a variable or function name is missing or misspelled.",
                "recommendations": [
                    "Check if the variable is defined before use.", 
                    "Check for spelling errors in variable names.",
                    "Ensure all necessary modules are imported."
                ],
                "confidence": 0.8,
                "rule_id": "rule_compile_recall"
            }
            
        # ADJUSTMENT: Syntax, Indentation, Type, Attribute
        if any(x in msg for x in ["syntaxerror", "indentationerror", "typeerror", "attributeerror", "invalid syntax"]):
             return {
                "err_type_pedagogical": "ADJUSTMENT",
                "natural_language": "There is a syntax structure or type mismatch issue.",
                "recommendations": [
                    "Check indentation levels.", 
                    "Check matching parentheses and colons.",
                    "Verify function argument types."
                ],
                "confidence": 0.8,
                "rule_id": "rule_compile_adjustment"
            }
            
        # Fallback
        return {
            "err_type_pedagogical": "ADJUSTMENT", # Lean towards adjustment for unknown compile errors
             "natural_language": f"Compiler error detected: {msg[:50]}...",
             "recommendations": ["Read the error message line number.", "Check the syntax around the reported line."],
             "confidence": 0.5,
             "rule_id": "rule_compile_fallback"
        }

    def _classify_logic(self, tests_summary: Optional[str], diff_summary: Dict[str, Any]) -> Dict[str, Any]:
        # Logic is harder without deep analysis, use simple heuristics for MVP
        
        # If huge changes -> DECOMPOSITION
        if diff_summary.get("total_changes", 0) > 20:
            return {
                "err_type_pedagogical": "DECOMPOSITION",
                "natural_language": "Large changes detected with failing tests.",
                "recommendations": [
                    "Revert recent large changes and apply them incrementally.",
                    "Break down the problem into smaller functions."
                ],
                "confidence": 0.6,
                "rule_id": "rule_logic_decomposition_large_change"
            }
            
        # MODIFICATION default
        return {
            "err_type_pedagogical": "MODIFICATION",
            "natural_language": "Code runs but logic seems incorrect.",
            "recommendations": [
                "Check boundary conditions (e.g., 0, empty list).", 
                "Add print statements to trace variable values.",
                "Verify loop termination conditions."
            ],
            "confidence": 0.5,
            "rule_id": "rule_logic_modification_default"
        }

    def _add_bridging_fields(self, result: Dict[str, Any]) -> Dict[str, Any]:
        ptype = result.get("err_type_pedagogical", "UNKNOWN")
        
        # Default bridging values
        ceiling = None
        leaf_start = None
        
        if ptype == "RECALL":
            ceiling = 1
            leaf_start = "L0"
        elif ptype == "ADJUSTMENT":
            ceiling = 2
            leaf_start = "L1"
        elif ptype == "MODIFICATION":
            ceiling = 2
            leaf_start = "L1"
        elif ptype == "DECOMPOSITION":
            ceiling = 2
            leaf_start = "L2"
            
        result["suggested_ceiling"] = ceiling
        result["suggested_leaf_start_level"] = leaf_start
        # We store rule_id in the result already, but key is "rule_id".
        # Caller (DiagnosisPipeline) should map it to debug.ceiling_rule_id if needed, 
        # or we can rename it here if we want consistency. 
        # The prompt asks for `debug.ceiling_rule_id`.
        # I'll let pipeline handle the mapping or just rely on `rule_id` being present.
        
        return result
