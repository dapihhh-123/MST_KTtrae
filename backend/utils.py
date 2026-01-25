import uuid
import time

def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def now() -> float:
    return time.time()
