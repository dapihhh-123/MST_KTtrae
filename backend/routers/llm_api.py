from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.llm_service import llm_service
from backend.services.prompting import build_intervention_prompt
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

router = APIRouter()

class InterventionRequest(BaseModel):
    diagnose_result: Dict[str, Any]
    code_excerpt: str
    event_type: str
    ceiling: int = 2
    mode: str = "logic_help"

@router.post("/llm/generate_intervention")
def generate_intervention(req: InterventionRequest):
    """
    Generate intervention message using LLM based on diagnosis.
    """
    # 1. Build Prompt
    # Need to reconstruct event object-like structure or dict
    class MockEvent:
        def __init__(self, t): self.type = t
    
    event = MockEvent(req.event_type)
    
    prompt_msgs = build_intervention_prompt(
        diagnose_result=req.diagnose_result,
        code_excerpt=req.code_excerpt,
        event=event,
        ceiling=req.ceiling,
        mode=req.mode
    )
    
    # 2. Call LLM
    # Assuming llm_service has a method for chat completion
    # If not, we use generate_hint which takes string. 
    # Let's flatten prompt_msgs to string for simple generate_hint or add chat support.
    # prompt_msgs is list of dicts.
    
    # Check llm_service capabilities. 
    # For now, let's just convert to string prompt if generate_hint expects string.
    full_prompt = "\n".join([f"{m['role']}: {m['content']}" for m in prompt_msgs])
    
    response = llm_service.generate_hint(full_prompt)
    
    return {"assistant_message": response}

class StreamRequest(BaseModel):
    prompt: str
    
from fastapi.responses import StreamingResponse

@router.post("/ai/write/stream")
def ai_write_stream(req: StreamRequest):
    """
    Stream LLM output for code writing.
    """
    def generator():
        # Call LLM Stream (Sync)
        try:
            for chunk in llm_service.stream_completion([{"role": "user", "content": req.prompt}]):
                yield chunk
        except Exception as e:
            yield f"[Error: {e}]"

    return StreamingResponse(generator(), media_type="text/plain")
