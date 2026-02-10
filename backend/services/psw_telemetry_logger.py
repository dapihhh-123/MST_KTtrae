import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Dict, Any, List


@dataclass
class TelemetryBatch:
    session_id: str
    events: List[Dict[str, Any]]


class PSWTelemetryLogger:
    def __init__(self, repo_root: Path | None = None):
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]

    def _log_path(self, session_id: str) -> Path:
        return self._repo_root / "telemetry" / f"{session_id}.jsonl"

    def append_batch(self, batch: TelemetryBatch) -> Path:
        path = self._log_path(batch.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for event in batch.events:
                record = {
                    "session_id": batch.session_id,
                    **event,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def read(self, session_id: str) -> str:
        path = self._log_path(session_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")


psw_telemetry_logger = PSWTelemetryLogger()
