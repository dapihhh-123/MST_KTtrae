from fastapi import APIRouter, HTTPException, Body
from backend.services.llm_service import llm_service
from backend.services.websocket_service import manager
from backend import schemas, utils
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger("Backend")
router = APIRouter()

class AIWriteRequest(BaseModel):
    session_id: str
    instruction: str
    code_context: str
    thread_id: Optional[str] = None
    target_range: Optional[Dict[str, Any]] = None # {start_line, end_line}

@router.post("/ai/write")
async def ai_write(req: AIWriteRequest):
    session_id = req.session_id
    thread_id = req.thread_id or "ai_write_thread"
    
    # 1. Notify Thinking
    await manager.broadcast(session_id, {
        "type": "ai_state",
        "state": "thinking",
        "scope": "global", # or breakout
        "thread_id": thread_id
    })
    
    # 2. Prepare LLM Call with Tools
    system_prompt = """You are an expert coding assistant. 
You MUST update the user's code based on their instruction.
You MUST use the 'update_code' tool to return the changes.
Do NOT return plain text code.
Return a LIST of operations (replace, insert, delete).
For 'replace', provide the range and the new text.
For 'insert', provide the position (line/col) and text.
For 'delete', provide the range.
"""
    
    user_msg = f"""
Code Context:
{req.code_context}

Instruction: {req.instruction}
"""
    if req.target_range:
        user_msg += f"\nTarget Range: Lines {req.target_range.get('start_line')} - {req.target_range.get('end_line')}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg}
    ]
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "update_code",
                "description": "Apply structured edits to the code",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ops": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "op": {"type": "string", "enum": ["replace", "insert", "delete"]},
                                    "range": {
                                        "type": "object",
                                        "properties": {
                                            "start_line": {"type": "integer"},
                                            "start_col": {"type": "integer"},
                                            "end_line": {"type": "integer"},
                                            "end_col": {"type": "integer"}
                                        },
                                        "required": ["start_line", "end_line"]
                                    },
                                    "text": {"type": "string"}
                                },
                                "required": ["op", "range"]
                            }
                        }
                    },
                    "required": ["ops"]
                }
            }
        }
    ]
    
    try:
        # 3. Call LLM
        response = llm_service.chat(
            messages=messages,
            model="gpt-4o-mini",
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "update_code"}}
        )
        
        # 4. Process Tool Call
        tool_calls = response["raw"].choices[0].message.tool_calls
        if not tool_calls:
            # Fallback if model refused to call tool (rare with tool_choice forced)
            raise ValueError("Model did not return code edits.")
            
        function_args = json.loads(tool_calls[0].function.arguments)
        ops = function_args.get("ops", [])
        
        # 5. Broadcast Ops
        await manager.broadcast(session_id, {
            "type": "ai_state",
            "state": "writing",
            "thread_id": thread_id
        })
        
        await manager.broadcast(session_id, {
            "type": "editor_ops",
            "ops": ops
        })
        
        # 6. Notify Done
        await manager.broadcast(session_id, {
            "type": "ai_state",
            "state": "done",
            "thread_id": thread_id
        })
        
        return {"status": "ok", "ops_count": len(ops)}
        
    except Exception as e:
        logger.error(f"AI Write Error: {e}")
        await manager.broadcast(session_id, {
            "type": "ai_state",
            "state": "error",
            "thread_id": thread_id,
            "meta": {"error": str(e)}
        })
        raise HTTPException(status_code=500, detail=str(e))
