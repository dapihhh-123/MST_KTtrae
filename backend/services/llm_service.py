import openai
from backend.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL, LLM_TIMEOUT_SECONDS
from typing import Generator, Optional, List, Dict, Any
import logging
import time

logger = logging.getLogger("Backend")

class LLMService:
    def __init__(self):
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY is not set. LLM features will fail.")
            self.client = None
        else:
            self.client = openai.OpenAI(
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
                timeout=LLM_TIMEOUT_SECONDS
            )

    def chat(self, messages: List[Dict[str, str]], 
             model: str = OPENAI_MODEL, 
             temperature: float = 0.7, 
             max_tokens: Optional[int] = None,
             tools: Optional[List[Dict]] = None,
             tool_choice: Optional[Any] = None) -> Dict[str, Any]:
        """
        Unified chat method with error handling and standard response format.
        """
        if not self.client:
            raise RuntimeError("LLM client not initialized (missing API key).")

        start_time = time.time()
        try:
            # Prepare kwargs, filtering None values
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            if tools:
                kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

            response = self.client.chat.completions.create(**kwargs)
            
            # Extract content
            message = response.choices[0].message
            content = message.content
            
            # Usage
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            } if response.usage else {}
            
            return {
                "text": content,
                "raw": response,
                "usage": usage,
                "latency_ms": int((time.time() - start_time) * 1000)
            }
            
        except openai.RateLimitError:
            logger.error("LLM Rate Limit Exceeded")
            raise RuntimeError("Rate limit exceeded. Please try again later.")
        except openai.APIConnectionError:
            logger.error("LLM Connection Error")
            raise RuntimeError("Connection error. Please check network.")
        except openai.APIStatusError as e:
            logger.error(f"LLM API Error: {e.status_code} - {e.message}")
            raise RuntimeError(f"LLM Provider Error: {e.message}")
        except Exception as e:
            logger.error(f"LLM Unexpected Error: {e}")
            raise RuntimeError(f"Unexpected error: {str(e)}")

    def generate_hint(self, context: str, model: str = OPENAI_MODEL) -> str:
        """
        Legacy wrapper for simple hint generation.
        """
        messages = [
            {"role": "system", "content": "You are a helpful coding tutor."},
            {"role": "user", "content": context}
        ]
        try:
            result = self.chat(messages, model=model)
            return result["text"]
        except Exception as e:
            return f"Error generating hint: {str(e)}"

    def stream_completion(self, messages: list, model: str = OPENAI_MODEL) -> Generator[str, None, None]:
        """
        Streaming generation for 'AI typing' effect.
        """
        if not self.client:
            yield "LLM service unavailable."
            return

        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM Stream Error: {e}")
            yield f"[Error: {e}]"

llm_service = LLMService()
