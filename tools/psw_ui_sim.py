import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools.replay_psw import PSWConfig, PSWDetector, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate UI PSW state changes from JSONL.")
    parser.add_argument("jsonl", help="Path to telemetry JSONL")
    parser.add_argument("--config", help="Optional JSON config for thresholds")
    args = parser.parse_args()

    config: PSWConfig = load_config(args.config)
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
    last_state = None
    sustain_start = None

    for event in events:
        output = detector.ingest(event)
        ts = event.get("ts")
        if output["state"] != last_state:
            sustain_start = ts
            last_state = output["state"]
            print(f"{ts}\tstate_change\t{output['state']}")
        if output["state"] in ("Flailing", "Stalling") and sustain_start is not None and ts is not None:
            if ts - sustain_start >= config.PSW_SUSTAIN_SECONDS * 1000:
                print(f"{ts}\tbadge_shown\t{output['state']}")


if __name__ == "__main__":
    main()
