import time
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque

class TelemetryService:
    _instance = None

    def __init__(self):
        # session_id -> { key: value }
        self.metrics = defaultdict(lambda: {
            "last_activity_ts": time.time(),
            "last_activity_event_type": "none",
            "idle_ms": 0,
            
            # AI Suggestion Metrics (Rolling window logic simplified for MVP)
            "ai_suggestion_shown_count": 0,
            "ai_suggestion_accept_count": 0,
            "ai_patch_delta_chars": 0,
            
            # Event history for debug
            "events_history": deque(maxlen=100)
        })
        
        # Define active events that reset idle timer
        self.ACTIVE_EVENTS = {
            "edit", "paste", "undo", "redo", 
            "cursor_move", "selection", "help_request",
            "user_message" # Chat is active
        }

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def track_event(self, session_id: str, event_type: str, payload: Dict[str, Any]):
        data = self.metrics[session_id]
        now = time.time()
        
        # 1. Update Idle Logic
        if event_type in self.ACTIVE_EVENTS:
            data["last_activity_ts"] = now
            data["last_activity_event_type"] = event_type
            data["idle_ms"] = 0 # Reset
        else:
            # Passive event (compile, run, test, etc.) - just accumulate idle time based on diff?
            # Actually, idle_ms should be (now - last_activity_ts) * 1000
            # We don't need to "store" idle_ms strictly, we calculate it on query, 
            # but for the requirements "idle_ms must continue growing", calculation on query is best.
            pass
            
        # 2. Track AI Metrics
        if event_type == "ai_suggestion_shown":
            data["ai_suggestion_shown_count"] += 1
        elif event_type == "ai_suggestion_accepted":
            data["ai_suggestion_accept_count"] += 1
            data["ai_patch_delta_chars"] += payload.get("delta_chars", 0)
            
        # History
        data["events_history"].append({
            "type": event_type,
            "ts": now
        })

    def get_metrics(self, session_id: str) -> Dict[str, Any]:
        data = self.metrics[session_id]
        now = time.time()
        
        # Calculate dynamic idle_ms
        idle_ms = int((now - data["last_activity_ts"]) * 1000)
        
        # Calculate Ratio
        shown = data["ai_suggestion_shown_count"]
        accept = data["ai_suggestion_accept_count"]
        ratio = (accept / shown) if shown > 0 else 0.0
        
        return {
            "idle_ms": idle_ms,
            "last_activity_event_type": data["last_activity_event_type"],
            "last_activity_ts": data["last_activity_ts"],
            
            "ai_suggestion_shown_count_10m": shown, # Assuming reset or short session for MVP
            "ai_suggestion_accept_count_10m": accept,
            "ai_accept_ratio_10m": round(ratio, 2),
            "ai_patch_delta_chars_10m": data["ai_patch_delta_chars"]
        }

telemetry_service = TelemetryService.get_instance()
