from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from backend import models
import difflib

class DiagnosticContextBuilder:
    def __init__(self, db: Session):
        self.db = db

    def build(self, session_id: str, event_id: str) -> Dict[str, Any]:
        # 1. Fetch Event
        event = self.db.query(models.EventLog).filter(models.EventLog.id == event_id).first()
        if not event:
            # Fallback for manual testing if event_id doesn't exist
            event_payload = {}
        else:
            event_payload = event.payload

        # 2. Fetch Latest Snapshot
        snapshot = self.db.query(models.CodeSnapshot)\
            .filter(models.CodeSnapshot.session_id == session_id)\
            .order_by(models.CodeSnapshot.created_at.desc())\
            .first()
        
        current_code = snapshot.content if snapshot else ""

        # 3. Diff Summary (vs previous snapshot or empty)
        # Find previous snapshot
        prev_snapshot = None
        if snapshot:
             prev_snapshot = self.db.query(models.CodeSnapshot)\
                .filter(models.CodeSnapshot.session_id == session_id, models.CodeSnapshot.created_at < snapshot.created_at)\
                .order_by(models.CodeSnapshot.created_at.desc())\
                .first()
        
        prev_code = prev_snapshot.content if prev_snapshot else ""
        diff_summary = self._compute_diff_summary(prev_code, current_code)

        return {
            "session_id": session_id,
            "event_id": event_id,
            "event_payload": event_payload,
            "current_code": current_code,
            "diff_summary": diff_summary,
            "event": event
        }

    def _compute_diff_summary(self, old_code: str, new_code: str) -> Dict[str, Any]:
        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()
        
        diff = list(difflib.unified_diff(old_lines, new_lines, n=0))
        
        added = 0
        removed = 0
        
        for line in diff:
            if line.startswith('@@'):
                pass 
            elif line.startswith('+') and not line.startswith('+++'):
                added += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed += 1
                
        return {
            "added_lines": added,
            "removed_lines": removed,
            "total_changes": added + removed
        }
