
import uuid
import hashlib
import json

def new_uuid() -> str:
    return str(uuid.uuid4())

def truncate_utf8_bytes(s: str, max_bytes: int) -> str:
    if s is None: return ""
    if len(s.encode('utf-8')) <= max_bytes:
        return s
    return s.encode('utf-8')[:max_bytes].decode('utf-8', errors='ignore')

def compute_bundle_hash(spec_json, public_examples_json, hidden_tests_json, seed):
    data = {
        "spec": spec_json,
        "public": public_examples_json,
        "hidden": hidden_tests_json,
        "seed": seed
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def compute_initial_confidence(spec_json, confirmations=None):
    reasons = []
    conf = 0.9
    
    # Check 1: Goal
    if not spec_json.get("goal_one_liner"):
        conf -= 0.2
        reasons.append("missing_goal")
        
    # Check 2: Ambiguities
    # Only penalize user-facing ambiguities if they are NOT confirmed
    ambiguities = spec_json.get("ambiguities") or []
    
    # Check if all ambiguities are resolved
    all_resolved = False
    if confirmations and isinstance(confirmations, dict):
        selections = confirmations.get("selections") or {}
        # Get IDs of all ambiguities that need resolution
        needed_ids = []
        for a in ambiguities:
            if isinstance(a, dict) and a.get("ambiguity_id"):
                needed_ids.append(str(a.get("ambiguity_id")))
        
        # Check if all needed IDs are present in selections
        if needed_ids and all(aid in selections for aid in needed_ids):
            all_resolved = True
            
    if ambiguities and not all_resolved:
        conf = min(conf, 0.4) # Cap at 0.4 if user interaction needed
        reasons.append("has_ambiguities")
    elif ambiguities and all_resolved:
        reasons.append("ambiguities_resolved")
        
    # Check 3: Missing Constraints (New)
    constraints = spec_json.get("constraints") or []
    if not constraints:
        # If absolutely no constraints, confidence should be low
        conf = min(conf, 0.4)
        reasons.append("missing_constraints")
    elif len(constraints) < 2:
         # Weak constraints penalty
         conf -= 0.1
         reasons.append("weak_constraints")
         
    return max(0.0, conf), reasons

def compute_post_tests_confidence(initial, hidden_tests):
    reasons = []
    conf = initial
    if not hidden_tests:
        conf -= 0.1
        reasons.append("no_hidden_tests")
    return conf, reasons
