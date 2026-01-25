
import asyncio
import logging
from typing import Optional
from sqlalchemy.orm import Session
from backend.services.websocket_service import manager
from backend.services.llm_service import llm_service
from backend.services.chat_service import ChatService
from backend import schemas, utils

logger = logging.getLogger("Backend")

async def stream_and_persist_reply(
    session_id: str, 
    thread_id: str, 
    prompt: str, 
    db: Session,
    mode: str = "global"
) -> str:
    """
    Streams LLM reply to WebSocket and persists the full message to DB.
    Returns the created message_id.
    """
    
    # Generate ID for the message
    message_id = utils.uid("msg")
    
    try:
        # 1. Start Thinking
        await manager.broadcast(session_id, {"type": "ai_state", "state": "thinking", "thread_id": thread_id})
        # await asyncio.sleep(0.5) # Optional: visual pacing
        
        # 2. Start Writing (First Token)
        await manager.broadcast(session_id, {"type": "ai_state", "state": "writing", "thread_id": thread_id})
        
        # 3. Stream Chunks
        messages = [{"role": "user", "content": prompt}]
        # In a real app, we would include history here. 
        # For now, we rely on the caller to provide the full prompt or just use the prompt as is.
        
        full_content = ""
        seq = 0
        
        stream_gen = llm_service.stream_completion(messages)
        
        # Note: llm_service.stream_completion is a synchronous generator in current impl?
        # If it's blocking, we might block the event loop. 
        # ideally it should be async, but let's check llm_service.py again.
        # It calls client.chat.completions.create(stream=True) which returns a sync iterator.
        # So we iterate it synchronously. For high concurrency, run in executor.
        # For this demo/MVP, sync iteration in async def is acceptable but not ideal.
        
        for chunk in stream_gen:
            await manager.broadcast(session_id, {
                "type": "ai_text_chunk",
                "thread_id": thread_id,
                "message_id": message_id,
                "delta": chunk,
                "seq": seq,
                "is_final": False
            })
            full_content += chunk
            seq += 1
            # Yield control to event loop to allow other WS messages
            await asyncio.sleep(0) 
            
        # 4. Final Chunk (Empty) + Done
        await manager.broadcast(session_id, {
            "type": "ai_text_chunk",
            "thread_id": thread_id,
            "message_id": message_id,
            "delta": "",
            "seq": seq,
            "is_final": True
        })
        await manager.broadcast(session_id, {"type": "ai_state", "state": "done", "thread_id": thread_id})
        
        # 5. Persist to DB
        chat_service = ChatService(db)
        chat_service.add_message(
            thread_id, 
            schemas.MessageCreate(role="assistant", content=full_content),
            message_id=message_id
        )
        
        return message_id

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        await manager.broadcast(session_id, {
            "type": "ai_state", 
            "state": "error", 
            "message": str(e),
            "where": "llm_stream"
        })
        raise e
