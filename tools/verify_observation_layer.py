import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_latest_log(repo_root: Path) -> Optional[Path]:
    base = repo_root / "logs" / "observations"
    if not base.exists():
        return None
    candidates = list(base.rglob("*.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def load_lines(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    objs: List[Dict[str, Any]] = []
    raw_lines: List[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw_lines.append(line)
            objs.append(json.loads(line))
    return objs, raw_lines


def check_seq(events: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    last = None
    for e in events:
        seq = e.get("seq")
        if not isinstance(seq, int):
            return False, f"seq is not int: {seq}"
        if last is not None and seq <= last:
            return False, f"seq not increasing: prev={last} curr={seq}"
        last = seq
    return True, None


def check_snapshot_pairing(events: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    for i, e in enumerate(events):
        if e.get("event_type") != "run_start":
            continue
        if i == 0:
            problems.append(f"run_start at index {i} has no previous event")
            continue
        prev = events[i - 1]
        if prev.get("event_type") != "snapshot":
            problems.append(f"run_start at seq={e.get('seq')} not preceded by snapshot (prev={prev.get('event_type')})")
    return len(problems) == 0, problems


def find_failed_run_error(events: List[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    for e in events:
        if e.get("event_type") != "run_end":
            continue
        payload = e.get("payload") or {}
        success = payload.get("success")
        if success is True:
            continue
        if payload.get("error_type") and payload.get("error_line"):
            return True, payload
    return False, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if args.session_id:
        base = repo_root / "logs" / "observations"
        matches = list(base.rglob(f"{args.session_id}.jsonl"))
        if not matches:
            print("PASS/FAIL: FAIL")
            print(f"session_id: {args.session_id}")
            print("log_path: (not found)")
            print("reason: log file not found")
            return 1
        log_path = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    else:
        log_path = find_latest_log(repo_root)
        if not log_path:
            print("PASS/FAIL: FAIL")
            print("session_id: (unknown)")
            print("log_path: (not found)")
            print("reason: no logs found")
            return 1

    events, _ = load_lines(log_path)
    session_id = (events[0].get("session_id") if events else None) or log_path.stem

    counts = Counter([e.get("event_type") for e in events])
    total = len(events)

    ok_seq, seq_reason = check_seq(events)
    ok_pair, pair_problems = check_snapshot_pairing(events)
    ok_err, err_payload = find_failed_run_error(events)

    passed = ok_seq and ok_pair and ok_err and total > 0

    print(f"session_id: {session_id}")
    print(f"log_path: {log_path}")
    print(f"event_total: {total}")
    print("event_type_counts:")
    for k in sorted(counts.keys()):
        print(f"  - {k}: {counts[k]}")
    print(f"seq_monotonic_increasing: {'YES' if ok_seq else 'NO'}")
    if not ok_seq:
        print(f"seq_problem: {seq_reason}")
    print(f"snapshot_before_each_run_start: {'YES' if ok_pair else 'NO'}")
    if not ok_pair:
        for p in pair_problems[:20]:
            print(f"pair_problem: {p}")
    print("failed_run_end_error_extract:")
    if ok_err and err_payload:
        print(f"  error_type: {err_payload.get('error_type')}")
        print(f"  error_line: {err_payload.get('error_line')}")
    else:
        print("  error_type: (missing)")
        print("  error_line: (missing)")

    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

