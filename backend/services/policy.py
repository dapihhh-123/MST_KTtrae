from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import time
import random

# --- Data Structures ---
class ActionPlan(BaseModel):
    interrupt: bool
    target_thread_id: Optional[str] = None
    ui_actions: Dict[str, Any] = {} 
    assistant_message: Optional[str] = None
    need_llm: bool = False
    llm_mode: Optional[str] = None 
    ceiling: int = 3
    
    # New LEAF fields
    leaf_level: str = "L0" # L0, L1, L2, L3, L4
    unlock_required: bool = False
    unlock_question: Optional[Dict[str, Any]] = None # {type, content, options}
    fading_direction: Optional[str] = None # "upgrade", "downgrade", "stable"
    is_debt_recap: bool = False

# --- State Management ---
class SessionState:
    def __init__(self):
        self.cooldown_until = 0
        self.recent_failures = 0
        self.consecutive_successes = 0
        self.last_intervention_type = None
        
        # LEAF State
        self.current_leaf_level_idx = 0 # 0=L0, 1=L1, ...
        self.ceiling_idx = 3 # Default L3
        self.mastery_score = 0.0
        self.learning_debts = [] # List of debt items
        
        # Concept Tracking
        self.current_concept_id = "general"

_session_states = {}

def get_session_state(session_id: str) -> SessionState:
    if session_id not in _session_states:
        _session_states[session_id] = SessionState()
    return _session_states[session_id]

# --- LEAF Constants ---
LEAF_LEVELS = ["L0", "L1", "L2", "L3", "L4"]

# --- Policy Logic ---
def decide_action(
    event: Any, 
    diagnose_result: Dict[str, Any], 
    session_id: str,
    context: Dict[str, Any] = {}
) -> ActionPlan:
    
    state = get_session_state(session_id)
    now = time.time()
    
    # 0. Handle Subtask Boundary / Recap Trigger
    if event.type == "test_pass" or (event.type == "idle" and state.recent_failures == 0):
        return _handle_boundary_recap(state)

    # 0.5 Handle Unlock Attempt / Recap Response
    if event.type == "unlock_attempt":
        is_correct = event.payload.get("correct", False)
        if is_correct:
            # Correct: Unlock L3/L4 content
            # Could upgrade level or just return allow plan
            return ActionPlan(
                interrupt=True, # To show the unlocked content
                leaf_level=LEAF_LEVELS[state.current_leaf_level_idx],
                assistant_message="Correct! Here is the solution code.",
                ui_actions={"show_code": True},
                fading_direction="stable"
            )
        else:
            # Wrong: Downgrade to L2
            state.current_leaf_level_idx = 2 # L2
            state.recent_failures += 1 # Count as failure
            
            # Record Debt (3.6.2)
            state.learning_debts.append("concept_unlock_fail")
            
            return ActionPlan(
                interrupt=True,
                leaf_level="L2",
                assistant_message="Not quite. Let's step back to the skeleton (L2).",
                fading_direction="downgrade",
                unlock_required=False
            )
            
    if event.type == "recap_response":
        # Assume correctness check is done or we accept any engagement for MVP
        # Ideally, check payload['correct']
        resolve_debt(session_id)
        return ActionPlan(
            interrupt=True,
            assistant_message="Great job clearing that debt! Moving on.",
            is_debt_recap=False
        )

    # 1. Cooldown Check
    if now < state.cooldown_until:
        return ActionPlan(interrupt=False)
        
    # 2. Determine if we should interrupt (no model dependency)
    coarse = (diagnose_result.get("err_type_coarse") or diagnose_result.get("error_kind") or "UNKNOWN").upper()
    is_error = coarse in {"COMPILE", "LOGIC"}

    payload = getattr(event, "payload", {}) or {}
    run_result = payload.get("result")

    if event.type in {"run", "test"} and run_result == "Success":
        _handle_success(state)
        return ActionPlan(interrupt=False)

    should_interrupt = False
    if event.type in {"compile_error", "run_fail", "test_fail"}:
        should_interrupt = True
    elif event.type in {"run", "test"} and run_result and run_result != "Success":
        should_interrupt = True
    elif event.type == "idle" and state.recent_failures > 0:
        should_interrupt = True
    elif is_error:
        should_interrupt = True
    
    if not should_interrupt:
        return ActionPlan(interrupt=False)

    # 3. Determine Intervention Details (LEAF Logic)
    
    # 3.1 Update Failures & Fading (Upgrade)
    state.recent_failures += 1
    state.consecutive_successes = 0
    fading_dir = "stable"
    
    # Fading Rule: If failures > 2, upgrade level
    if state.recent_failures > 2:
        if state.current_leaf_level_idx < state.ceiling_idx:
            state.current_leaf_level_idx += 1
            fading_dir = "upgrade"
            state.recent_failures = 0 # Reset after upgrade
    
    # 3.2 Determine Mode & Ceiling
    # Use bridging fields if available
    suggested_ceiling = diagnose_result.get("suggested_ceiling")
    if suggested_ceiling is not None:
        state.ceiling_idx = min(suggested_ceiling + 1, 4) # Map 1->L2? Just use raw int for now.
        # Mapping: 1->L1(idx 1), 2->L2(idx 2). 
        # Actually Schema says ceiling is int. Let's assume it maps to LEAF_LEVELS index cap.
        state.ceiling_idx = int(suggested_ceiling) + 1 # e.g. ceiling=1 -> L1 (idx 1)
        if state.ceiling_idx >= len(LEAF_LEVELS): state.ceiling_idx = len(LEAF_LEVELS) - 1

    current_leaf = LEAF_LEVELS[state.current_leaf_level_idx]
    
    # 3.3 Check Debt
    is_debt = False
    if state.learning_debts:
        is_debt = True
        # Force debt recap mode if debts exist
        # We'll attach a debt recap prompt instruction later
    
    # 3.4 Unlock Check
    unlock_req = False
    unlock_q = None
    if state.current_leaf_level_idx >= 3: # L3 or L4
        unlock_req = True
        unlock_q = {
            "type": "prediction",
            "content": "What will be the value of 'x' after the loop?",
            "options": ["10", "11", "9", "RuntimeError"]
        }

    evidence = diagnose_result.get("evidence") or {}
    spans = evidence.get("spans") or diagnose_result.get("spans") or []
    highlight_spans = []
    for s in spans:
        try:
            highlight_spans.append({
                "line_start": int(s.get("start_line") or s.get("line_start") or 1),
                "line_end": int(s.get("end_line") or s.get("line_end") or 1),
                "score": s.get("score")
            })
        except Exception:
            continue

    mode = "compile_help" if coarse == "COMPILE" or event.type == "compile_error" else "logic_help"
    
    # Update Cooldown
    state.cooldown_until = now + 10 # Short cooldown for demo
    
    plan = ActionPlan(
        interrupt=True,
        ui_actions={"highlight_spans": highlight_spans},
        need_llm=True,
        llm_mode=mode,
        ceiling=state.ceiling_idx,
        leaf_level=current_leaf,
        unlock_required=unlock_req,
        unlock_question=unlock_q,
        fading_direction=fading_dir,
        is_debt_recap=is_debt
    )
    
    return plan

def _handle_success(state: SessionState):
    state.recent_failures = 0
    state.consecutive_successes += 1
    
    # Mastery Update
    state.mastery_score = min(1.0, state.mastery_score + 0.1)
    
    # Fading (Downgrade)
    if state.consecutive_successes >= 2:
        if state.current_leaf_level_idx > 0:
            state.current_leaf_level_idx -= 1
            # Log downgrade? Captured in next intervention state

def _handle_boundary_recap(state: SessionState) -> ActionPlan:
    # Check debts
    is_debt = len(state.learning_debts) > 0
    
    return ActionPlan(
        interrupt=True,
        need_llm=True,
        llm_mode="debt_recap" if is_debt else "subtask_recap",
        leaf_level="L0", # Recap usually conversational
        is_debt_recap=is_debt,
        assistant_message="Let's recap what we just learned." # Placeholder
    )

# --- Helper to inject debt (for simulation) ---
def add_debt(session_id: str, concept_id: str):
    state = get_session_state(session_id)
    state.learning_debts.append(concept_id)

def resolve_debt(session_id: str):
    state = get_session_state(session_id)
    if state.learning_debts:
        state.learning_debts.pop(0)
        state.mastery_score += 0.05 # Bonus for resolving debt
        state.ceiling_idx = max(0, state.ceiling_idx - 1) # Reduce ceiling (more autonomy) as reward? 
        # Wait, reducing ceiling means *less* help allowed? 
        # "lower ceiling" usually means "lower MAX help", i.e. we don't give answers. Yes.
        # So success -> lower ceiling.
