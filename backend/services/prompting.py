from typing import List, Dict, Optional, Any
from backend import schemas

def build_chat_messages(
    thread_messages: List[schemas.Message],
    system_prompt: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, str]]:
    """
    Constructs the list of messages for the LLM chat API.
    """
    
    # Default System Prompt
    default_system = (
        "You are an expert AI programming assistant. "
        "Your goal is to help students learn by guiding them, not just giving answers. "
        "Be concise, encouraging, and pedagogically sound."
    )
    
    final_system_prompt = system_prompt or default_system
    
    # Inject Context if provided
    if extra_context:
        context_str = "\n\n[Current Context]:\n"
        
        if "code" in extra_context and extra_context["code"]:
            context_str += f"Code Snapshot:\n```\n{extra_context['code']}\n```\n"
            
        if "breakout_anchor" in extra_context and extra_context["breakout_anchor"]:
            anchor = extra_context["breakout_anchor"]
            context_str += f"Focus on: {anchor}\n"
            
        final_system_prompt += context_str

    messages = [{"role": "system", "content": final_system_prompt}]
    
    # Append thread history
    # Filter out invalid roles just in case
    valid_roles = {"user", "assistant", "system"}
    for msg in thread_messages:
        if msg.role in valid_roles:
            messages.append({"role": msg.role, "content": msg.content})
            
    return messages

def build_intervention_prompt(
    diagnose_result: Dict[str, Any],
    code_excerpt: str,
    event: Any, # EventLog model or schema
    ceiling: int = 2,
    mode: str = "logic_help"
) -> List[Dict[str, str]]:
    """
    Constructs a prompt for proactive intervention (no user message history yet).
    """
    
    # Base Instruction
    instruction = (
        "You are a coding tutor. The student encountered an issue. "
        "Do NOT give the full correct code immediately. "
        "Guide them step-by-step based on the pedagogical strategy below."
    )
    
    # Strategy
    strategies = {
        1: "Recall: Just point out where the error might be or ask a leading question.",
        2: "Adjustment: Give a strong hint or skeleton code, but leave gaps.",
        3: "Modification: Provide a partial fix for the specific error line, but explain why.",
        4: "Full Solution: Provide the complete solution."
    }
    strategy_desc = strategies.get(ceiling, strategies[2])
    
    # Mode Specific Instructions
    recap_instr = ""
    if mode == "debt_recap":
        recap_instr = """
        [Special Task: Debt Recap]
        The student previously struggled with a concept.
        1. Summarize the recent fix in 1 sentence.
        2. Ask a 'variant question' (e.g., 'What if x was 10?').
        3. Explicitly ask them to solve this variant to clear their 'Learning Debt'.
        """
    elif mode == "subtask_recap":
        recap_instr = """
        [Special Task: Subtask Recap]
        The student just completed a subtask/milestone.
        1. Summarize what was achieved in 1 sentence.
        2. Ask a 'variant question' to test generalization.
        """
    elif mode == "unlock_question":
         recap_instr = """
         [Special Task: Unlock Question]
         The student is about to see the solution (L3/L4).
         Generate a prediction question based on the code.
         """
    
    err_type_coarse = diagnose_result.get("err_type_coarse") or diagnose_result.get("error_kind") or "UNKNOWN"
    err_type_pedagogical = diagnose_result.get("err_type_pedagogical") or diagnose_result.get("teaching_kind") or "UNKNOWN"
    evidence = diagnose_result.get("evidence") or {}
    spans = evidence.get("spans") or diagnose_result.get("spans") or []
    
    diag_str = f"""
    [Diagnostics]
    - Coarse Type: {err_type_coarse}
    - Teaching Type: {err_type_pedagogical}
    - Spans: {spans}
    - Intervention Level: {ceiling} ({strategy_desc})
    - Mode: {mode}
    """
    
    # Event Info
    payload = getattr(event, "payload", {})
    event_str = f"""
    [Event]
    - Type: {event.type}
    - Payload: {payload}
    """
    
    # Code Context
    code_str = f"""
    [Code Excerpt]
    ```python
    {code_excerpt}
    ```
    """
    
    full_prompt = f"{instruction}\n{recap_instr}\n{diag_str}\n{event_str}\n{code_str}\n\nPlease generate a helpful, short message to the student."
    
    return [
        {"role": "system", "content": "You are an expert programming tutor."},
        {"role": "user", "content": full_prompt}
    ]
