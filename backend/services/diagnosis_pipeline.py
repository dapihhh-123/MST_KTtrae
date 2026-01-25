from sqlalchemy.orm import Session
from backend import models, schemas, utils
from backend.services.diagnostic_context import DiagnosticContextBuilder
from backend.services.pedagogical_classifier import PedagogicalClassifier
from backend.services.websocket_service import manager
import json
import logging
import random
from typing import Dict, Any

logger = logging.getLogger("Backend")

import hashlib
from typing import Dict, Any, Optional

# ...

class DiagnosisPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.context_builder = DiagnosticContextBuilder(db)
        self.classifier = PedagogicalClassifier()

    def resolve_thread_id(self, session_id: str, event_payload: Dict[str, Any]) -> str:
        # 1. Payload thread_id
        if event_payload.get("thread_id"):
            return event_payload["thread_id"]
            
        # 2. Payload marker_id -> Breakout
        if event_payload.get("marker_id"):
            marker = self.db.query(models.Marker).filter(models.Marker.id == event_payload["marker_id"]).first()
            if marker and marker.thread_id:
                return marker.thread_id
                
        # 3. Payload breakout_id -> Breakout (assuming breakout is a thread)
        if event_payload.get("breakout_id"):
            # Assuming breakout_id is thread_id in this schema
            return event_payload["breakout_id"]
            
        # 4. Default -> General
        general_thread = self.db.query(models.Thread)\
            .filter(models.Thread.session_id == session_id, models.Thread.type == "global")\
            .first()
            
        return general_thread.id if general_thread else "unknown_thread"

    def normalize_error_summary(self, error_msg: str) -> str:
        # Simple normalization: lower case, remove specific line numbers or paths if needed
        # For MVP: just strip whitespace and lower
        return error_msg.strip().lower()

    def compute_error_hash(self, summary: str) -> str:
        if not summary:
            return ""
        return hashlib.md5(summary.encode("utf-8")).hexdigest()

    async def run_diagnosis(self, session_id: str, event_id: str) -> schemas.DiagnosisResult:
        # 1. Build Context
        context = self.context_builder.build(session_id, event_id)
        current_code = context["current_code"]
        event_payload = context["event_payload"]
        diff_summary = context["diff_summary"]
        
        # Resolve Thread ID
        thread_id = self.resolve_thread_id(session_id, event_payload)
        
        # Resolve Trace ID
        trace_id = context.get("event").trace_id if context.get("event") else event_payload.get("trace_id")
        
        coarse_result = self._get_coarse_diagnosis(context, event_payload)
        
        # 3. Pedagogical Classification
        # Extract info from event_payload
        error_msg = event_payload.get("error", "") or event_payload.get("message", "") or event_payload.get("stderr", "")
        tests_summary = event_payload.get("tests_summary", "")
        
        # Override coarse type based on event type if available (for consistency)
        event_type = context.get("event", {}).type if context.get("event") else "unknown"
        if event_type == "compile_error":
            coarse_result["err_type_str"] = "COMPILE"
        elif event_type == "test_fail" or event_type == "run_fail":
            coarse_result["err_type_str"] = "LOGIC"
            
        # Ensure error summary for LOGIC
        if coarse_result["err_type_str"] == "LOGIC" and not error_msg and tests_summary:
             # Extract simple summary from test result if error_msg is empty
             error_msg = tests_summary.split("\n")[0][:100]
             
        pedagogical_result = self.classifier.classify(
            err_type_coarse=coarse_result.get("err_type_str", "UNKNOWN"),
            error_message=str(error_msg),
            diff_summary=diff_summary,
            tests_summary=tests_summary
        )
        
        # Hash Error
        norm_summary = self.normalize_error_summary(str(error_msg)[:200])
        err_hash = self.compute_error_hash(norm_summary)
        
        # 4. Assembly Evidence
        evidence = schemas.DiagnosisEvidence(
            spans=[
                schemas.DiagnosisSpan(
                    file="editor",
                    start_line=s[0], 
                    end_line=s[1], 
                    kind="attention", 
                    score=0.9
                ) for s in coarse_result.get("top_spans", [])
            ],
            error_summary=str(error_msg)[:200],
            error_hash=err_hash,
            tests_summary=str(tests_summary)[:200] if tests_summary else None,
            diff_summary=diff_summary,
            natural_language=pedagogical_result["natural_language"]
        )
        
        # 5. Create Result Object
        # Enhance Debug Info
        debug_info = coarse_result.get("debug", {})
        debug_info.update({
            "llm_used": False,
            "rule_id": pedagogical_result.get("rule_id"),
            "ceiling_rule_id": pedagogical_result.get("rule_id"), # Bridging
            "suggested_ceiling": pedagogical_result.get("suggested_ceiling"),
            "suggested_leaf_start_level": pedagogical_result.get("suggested_leaf_start_level"),
            "coarse_source": "rule"
        })
        
        result = schemas.DiagnosisResult(
            session_id=session_id,
            event_id=event_id,
            thread_id=thread_id,
            trace_id=trace_id,
            err_type_coarse=coarse_result.get("err_type_str", "UNKNOWN"),
            err_type_pedagogical=pedagogical_result["err_type_pedagogical"],
            confidence=pedagogical_result.get("confidence", 0.5),
            evidence=evidence,
            recommendations=pedagogical_result["recommendations"],
            suggested_ceiling=pedagogical_result.get("suggested_ceiling"),
            suggested_leaf_start_level=pedagogical_result.get("suggested_leaf_start_level"),
            debug=debug_info
        )
        
        # 6. Save to DB
        self._save_to_db(result)
        
        # 7. Notify WS
        await self._notify_ws(session_id, result)
        
        return result
        
    def _get_coarse_diagnosis(self, context, event_payload) -> Dict[str, Any]:
        err_map = {0: "CORRECT", 1: "COMPILE", 2: "LOGIC"}
        
        # Determine based on payload for realism
        err_type_val = 0
        if "error" in event_payload or "compile" in str(event_payload):
            err_type_val = 1
        elif "fail" in str(event_payload):
            err_type_val = 2
            
        return {
            "err_type_str": err_map.get(err_type_val, "UNKNOWN"),
            "top_spans": [(1, 5), (10, 12)],
            "debug": {"logit": 0.1, "simulated": True}
        }

    def _save_to_db(self, result: schemas.DiagnosisResult):
        db_log = models.DiagnosisLog(
            id=utils.uid("diag"),
            session_id=result.session_id,
            event_id=result.event_id,
            thread_id=result.thread_id,
            trace_id=result.trace_id,
            code_state_id=None, # To be filled if available in context
            err_type_coarse=result.err_type_coarse,
            err_type_pedagogical=result.err_type_pedagogical,
            confidence=result.confidence,
            evidence_json=result.evidence.model_dump(),
            recommendations_json=result.recommendations,
            debug_json=result.debug
        )
        self.db.add(db_log)
        self.db.commit()


    async def _notify_ws(self, session_id: str, result: schemas.DiagnosisResult):
        payload = {
            "type": "diagnosis_ready",
            "data": {
                "label": result.err_type_pedagogical,
                "evidence": result.evidence.natural_language,
                "recommendations": result.recommendations,
                "spans": [s.model_dump() for s in result.evidence.spans],
                "thread_id": result.thread_id,
                "trace_id": result.trace_id
            }
        }
        await manager.broadcast(session_id, payload)
        
        # Send highlight spans separately as requested
        highlight_payload = {
            "type": "highlight_spans",
            "data": {
                "spans": [s.model_dump() for s in result.evidence.spans],
                "trace_id": result.trace_id
            }
        }
        await manager.broadcast(session_id, highlight_payload)
