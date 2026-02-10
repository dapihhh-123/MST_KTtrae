import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class PSWConfig:
    IDLE_CUTOFF_SECONDS: int = 60
    T_ACTIVE_SECONDS: int = 120
    RUN_GAP_SECONDS: int = 90
    FLAIL_RUNS: int = 3
    MIN_CHAR_CHANGE: int = 20
    MIN_EDIT_EVENTS: int = 12
    SMALL_EDIT: int = 5
    PSW_SUSTAIN_SECONDS: int = 20


PSW_VERSION = "1.0.0"


class PSWDetector:
    def __init__(self, config: PSWConfig):
        self.config = config
        self.last_event_ts = None
        self.last_activity_ts = None
        self.last_run_ts = None
        self.chunk_active_seconds = 0.0
        self.chunk_runs = 0
        self.chunk_max_idle_seconds = 0.0
        self.chunk_edit_chars = 0
        self.chunk_edit_events = 0
        self.chunk_small_edit_events = 0
        self.S = 0.0
        self.S_best = 0.0
        self.last_pabs = None
        self.last_theta = None
        self.last_total_tests = None
        self.last_sig_info = None

    def ingest(self, event: Dict[str, Any]) -> Dict[str, Any]:
        ts = event.get("ts")
        if ts is None or not isinstance(ts, (int, float)):
            return self._output("In-PSW", "invalid_ts")
        if not self._advance_time(event):
            return self._output("In-PSW", "invalid_or_out_of_order_ts")
        if event.get("type") == "run_tests":
            self._apply_run_tests(event)
        if event.get("type") == "edit":
            self._apply_edit(event)
        if event.get("type") == "run_program":
            self.last_activity_ts = ts
        if event.get("type") == "idle_heartbeat":
            self._apply_idle(event)
        return self._compute_state()

    def _advance_time(self, event: Dict[str, Any]) -> None:
        ts = event.get("ts")
        if self.last_event_ts is not None and ts < self.last_event_ts:
            return False
        if self.last_event_ts is not None and ts > self.last_event_ts:
            delta_sec = (ts - self.last_event_ts) / 1000.0
            idle_seconds = self._derive_idle(event)
            if idle_seconds <= self.config.IDLE_CUTOFF_SECONDS:
                self.chunk_active_seconds += delta_sec
        self.last_event_ts = ts
        return True

    def _derive_idle(self, event: Dict[str, Any]) -> float:
        if event.get("type") == "idle_heartbeat":
            return float(event.get("payload", {}).get("idle_seconds_since_last_activity", 0) or 0)
        return 0.0

    def _apply_run_tests(self, event: Dict[str, Any]) -> None:
        payload = event.get("payload", {})
        pass_count = float(payload.get("pass_count", 0) or 0)
        total_tests = float(payload.get("total_tests", 0) or 0)
        if total_tests <= 0:
            self.S = 0.0
            self.last_pabs = 0.0
            self.last_theta = None
            self.last_total_tests = None
            self.last_run_ts = event.get("ts")
            self.last_activity_ts = event.get("ts")
            return
        S = pass_count / total_tests
        prev_best = self.S_best
        self.S = S
        if S > self.S_best:
            self.S_best = S
        theta = 1 / total_tests
        Pabs = max(self.S_best - prev_best, 0)
        self.last_pabs = Pabs
        self.last_theta = theta
        self.last_total_tests = total_tests
        if Pabs >= theta:
            self.last_sig_info = {
                "pre_chunk_active_time": self.chunk_active_seconds,
                "pre_chunk_runs": self.chunk_runs,
                "pre_chunk_max_idle": self.chunk_max_idle_seconds,
                "pre_chunk_edit_chars": self.chunk_edit_chars,
                "pre_chunk_small_edit_events": self.chunk_small_edit_events,
            }
            self._reset_chunk()
        else:
            self.chunk_runs += 1
        self.last_run_ts = event.get("ts")
        self.last_activity_ts = event.get("ts")

    def _apply_edit(self, event: Dict[str, Any]) -> None:
        payload = event.get("payload", {})
        delta = abs(int(payload.get("delta_chars", 0) or 0))
        self.chunk_edit_chars += delta
        self.chunk_edit_events += 1
        if delta <= self.config.SMALL_EDIT:
            self.chunk_small_edit_events += 1
        self.last_activity_ts = event.get("ts")

    def _apply_idle(self, event: Dict[str, Any]) -> None:
        payload = event.get("payload", {})
        idle = float(payload.get("idle_seconds_since_last_activity", 0) or 0)
        self.chunk_max_idle_seconds = max(self.chunk_max_idle_seconds, idle)

    def _reset_chunk(self) -> None:
        self.chunk_active_seconds = 0.0
        self.chunk_runs = 0
        self.chunk_max_idle_seconds = 0.0
        self.chunk_edit_chars = 0
        self.chunk_edit_events = 0
        self.chunk_small_edit_events = 0

    def _compute_state(self) -> Dict[str, Any]:
        if self.last_sig_info:
            reason = "significant_progress(Pabs>=theta) sig_progress=true reset_chunk"
            output = self._output("In-PSW", self._reason(reason))
            self.last_sig_info = None
            return output
        if self.chunk_active_seconds <= self.config.T_ACTIVE_SECONDS:
            return self._output("In-PSW", self._reason("active_time_within_threshold"))

        low_edits = self.chunk_edit_chars < self.config.MIN_CHAR_CHANGE
        many_small_edits = self.chunk_edit_events >= self.config.MIN_EDIT_EVENTS and low_edits
        long_idle = self.chunk_max_idle_seconds >= self.config.IDLE_CUTOFF_SECONDS
        long_no_run = self.last_run_ts is None
        run_gap_seconds = None
        if self.last_run_ts is not None and self.last_event_ts is not None:
            run_gap_seconds = max(0, (self.last_event_ts - self.last_run_ts) / 1000.0)
        long_run_gap = run_gap_seconds is not None and run_gap_seconds >= self.config.RUN_GAP_SECONDS

        flailing = self.chunk_runs >= self.config.FLAIL_RUNS and not long_no_run
        stalling = (long_idle and self.chunk_runs <= 1) or (low_edits and long_idle) or long_run_gap

        if flailing or many_small_edits:
            reason = "runs_without_progress" if flailing else "many_small_edits_without_progress"
            return self._output("Flailing", self._reason(reason))
        if stalling or (long_no_run and low_edits):
            reason = "idle_and_few_runs" if stalling else "no_runs_and_low_edits"
            return self._output("Stalling", self._reason(reason))
        return self._output("In-PSW", self._reason("default_in_psw"))

    def _output(self, state: str, reason: str) -> Dict[str, Any]:
        return {
            "state": state,
            "reason": reason,
            "metrics": {
                "S": self.S,
                "S_best": self.S_best,
                "chunk_active_time": self.chunk_active_seconds,
                "chunk_runs": self.chunk_runs,
                "chunk_max_idle": self.chunk_max_idle_seconds,
                "chunk_edit_chars": self.chunk_edit_chars,
                "chunk_edit_events": self.chunk_edit_events,
                "chunk_small_edit_events": self.chunk_small_edit_events,
                "pre_chunk_active_time": getattr(self, "last_sig_info", None) and self.last_sig_info.get("pre_chunk_active_time"),
                "pre_chunk_runs": getattr(self, "last_sig_info", None) and self.last_sig_info.get("pre_chunk_runs"),
                "pre_chunk_max_idle": getattr(self, "last_sig_info", None) and self.last_sig_info.get("pre_chunk_max_idle"),
                "pre_chunk_edit_chars": getattr(self, "last_sig_info", None) and self.last_sig_info.get("pre_chunk_edit_chars"),
                "pre_chunk_small_edit_events": getattr(self, "last_sig_info", None) and self.last_sig_info.get("pre_chunk_small_edit_events"),
                "last_run_ts": self.last_run_ts,
                "last_activity_ts": self.last_activity_ts,
            },
            "thresholds": {
                "IDLE_CUTOFF_SECONDS": self.config.IDLE_CUTOFF_SECONDS,
                "T_ACTIVE_SECONDS": self.config.T_ACTIVE_SECONDS,
                "RUN_GAP_SECONDS": self.config.RUN_GAP_SECONDS,
                "FLAIL_RUNS": self.config.FLAIL_RUNS,
                "MIN_CHAR_CHANGE": self.config.MIN_CHAR_CHANGE,
                "MIN_EDIT_EVENTS": self.config.MIN_EDIT_EVENTS,
                "SMALL_EDIT": self.config.SMALL_EDIT,
                "PSW_SUSTAIN_SECONDS": self.config.PSW_SUSTAIN_SECONDS,
                "theta": self.last_theta,
                "total_tests": self.last_total_tests,
                "psw_version": PSW_VERSION,
                "config_hash": config_hash(self.config),
            },
        }

    def _reason(self, label: str) -> str:
        return (
            f"{label} over_threshold={self.chunk_active_seconds > self.config.T_ACTIVE_SECONDS} "
            f"chunk_active_time={self.chunk_active_seconds:.1f} "
            f"chunk_runs={self.chunk_runs} chunk_max_idle={self.chunk_max_idle_seconds:.1f} "
            f"small_edits={self.chunk_small_edit_events} "
            f"Pabs={self.last_pabs} theta={self.last_theta} T_active={self.config.T_ACTIVE_SECONDS}"
        )


def load_config(path: str | None) -> PSWConfig:
    if not path:
        return PSWConfig()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PSWConfig(**data)


def config_hash(config: PSWConfig) -> str:
    payload = {
        "IDLE_CUTOFF_SECONDS": config.IDLE_CUTOFF_SECONDS,
        "T_ACTIVE_SECONDS": config.T_ACTIVE_SECONDS,
        "RUN_GAP_SECONDS": config.RUN_GAP_SECONDS,
        "FLAIL_RUNS": config.FLAIL_RUNS,
        "MIN_CHAR_CHANGE": config.MIN_CHAR_CHANGE,
        "MIN_EDIT_EVENTS": config.MIN_EDIT_EVENTS,
        "SMALL_EDIT": config.SMALL_EDIT,
        "PSW_SUSTAIN_SECONDS": config.PSW_SUSTAIN_SECONDS,
    }
    return json.dumps(payload, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay PSW telemetry JSONL.")
    parser.add_argument("jsonl", help="Path to telemetry/<session_id>.jsonl")
    parser.add_argument("--config", help="Optional JSON config for thresholds")
    parser.add_argument("--verbose", action="store_true", help="Print verbose metrics and reasons")
    args = parser.parse_args()

    config = load_config(args.config)
    detector = PSWDetector(config)

    lines = Path(args.jsonl).read_text(encoding="utf-8").splitlines()
    events: List[Dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    events.sort(key=lambda e: e.get("ts", 0))
    sustain_start = None
    last_state = None
    for event in events:
        output = detector.ingest(event)
        metrics = output["metrics"]
        if last_state != output["state"]:
            sustain_start = event.get("ts")
            last_state = output["state"]
        badge_shown = False
        if output["state"] in ("Flailing", "Stalling") and sustain_start is not None:
            if event.get("ts") is not None and (event.get("ts") - sustain_start) >= config.PSW_SUSTAIN_SECONDS * 1000:
                badge_shown = True
        if args.verbose:
            thresholds = output["thresholds"]
            print(
                f"{event.get('ts')}\t{output['state']}\t"
                f"S={metrics['S']:.2f}\tS_best={metrics['S_best']:.2f}\t"
                f"Pabs={detector.last_pabs}\ttheta={thresholds.get('theta')}\t"
                f"active={metrics['chunk_active_time']:.1f}s\tT_ACTIVE={thresholds.get('T_ACTIVE_SECONDS')}\t"
                f"runs={metrics['chunk_runs']}\tmax_idle={metrics['chunk_max_idle']:.1f}s\t"
                f"IDLE_CUTOFF={thresholds.get('IDLE_CUTOFF_SECONDS')}\t"
                f"run_gap={detector.last_event_ts and detector.last_run_ts and max(0, (detector.last_event_ts - detector.last_run_ts) / 1000.0)}\t"
                f"edit_chars={metrics['chunk_edit_chars']}\t"
                f"small_edit_count={metrics['chunk_small_edit_events']}\t"
                f"pre_reset_active={metrics.get('pre_chunk_active_time')}\t"
                f"pre_reset_runs={metrics.get('pre_chunk_runs')}\t"
                f"pre_reset_max_idle={metrics.get('pre_chunk_max_idle')}\t"
                f"pre_reset_edit_chars={metrics.get('pre_chunk_edit_chars')}\t"
                f"pre_reset_small_edits={metrics.get('pre_chunk_small_edit_events')}\t"
                f"psw_version={thresholds.get('psw_version')}\t"
                f"config_hash={thresholds.get('config_hash')}\t"
                f"badge={badge_shown}\t"
                f"reason={output['reason']}"
            )
        else:
            print(
                f"{event.get('ts')}\t{output['state']}\t"
                f"S={metrics['S']:.2f}\tS_best={metrics['S_best']:.2f}\t"
                f"active={metrics['chunk_active_time']:.1f}s\t"
                f"runs={metrics['chunk_runs']}\tmax_idle={metrics['chunk_max_idle']:.1f}s"
            )


if __name__ == "__main__":
    main()
