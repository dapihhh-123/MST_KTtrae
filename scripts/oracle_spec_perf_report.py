import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


def _load_json_maybe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value
    try:
        return json.loads(s)
    except Exception:
        return value


def _ts(epoch: Any) -> str:
    try:
        return datetime.datetime.fromtimestamp(float(epoch)).isoformat(timespec="seconds")
    except Exception:
        return str(epoch)


def _first_fail_reason(attempt_fail_reasons_json: Any) -> str:
    fr = _load_json_maybe(attempt_fail_reasons_json)
    if isinstance(fr, list) and fr:
        return str(fr[0])[:180]
    if fr is None:
        return ""
    return str(fr)[:180]


def _extract_deliverable(spec_json: Any) -> Optional[str]:
    spec = _load_json_maybe(spec_json)
    if isinstance(spec, dict):
        d = spec.get("deliverable")
        return str(d) if d is not None else None
    return None


def main() -> None:
    db_path = "backend.db"
    if not os.path.exists(db_path):
        db_path = r"c:\Users\dapi\Desktop\MST_KTtrae\backend.db"
    if not os.path.exists(db_path):
        raise SystemExit(f"Database not found: {db_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    print("== Latest 20 spec versions ==")
    rows = cur.execute(
        """
        SELECT
            version_id, task_id, version_number, status, created_at,
            llm_provider_used, llm_model_used, spec_llm_request_id,
            attempts, llm_latency_ms,
            spec_json, attempt_fail_reasons_json
        FROM oracle_task_versions
        ORDER BY created_at DESC
        LIMIT 20
        """
    ).fetchall()
    for r in rows:
        print(
            _ts(r["created_at"]),
            r["version_id"],
            "status=",
            r["status"],
            "attempts=",
            r["attempts"],
            "lat_ms=",
            r["llm_latency_ms"],
            "model=",
            r["llm_provider_used"],
            r["llm_model_used"],
            "deliverable=",
            _extract_deliverable(r["spec_json"]),
            "fail0=",
            _first_fail_reason(r["attempt_fail_reasons_json"]),
        )

    print("\n== Find receipts-related rows (keyword scan in spec_llm_raw_json) ==")
    keywords = [
        "clean_receipt",
        "receipt.txt",
        "cleaned.csv",
        "invalid_lines.txt",
        "grand_total",
        "BANANA",
        "苹果",
        "牛奶",
    ]
    where = " OR ".join(["spec_llm_raw_json LIKE ?" for _ in keywords])
    params = [f"%{k}%" for k in keywords]
    rows = cur.execute(
        f"""
        SELECT
            version_id, status, created_at, attempts, llm_latency_ms,
            llm_provider_used, llm_model_used,
            attempt_fail_reasons_json
        FROM oracle_task_versions
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT 10
        """,
        params,
    ).fetchall()
    print("matched", len(rows))
    for r in rows:
        print(
            _ts(r["created_at"]),
            r["version_id"],
            "status=",
            r["status"],
            "attempts=",
            r["attempts"],
            "lat_ms=",
            r["llm_latency_ms"],
            "model=",
            r["llm_provider_used"],
            r["llm_model_used"],
            "fail0=",
            _first_fail_reason(r["attempt_fail_reasons_json"]),
        )

    print("\n== Top 10 slowest spec calls (by llm_latency_ms) ==")
    rows = cur.execute(
        """
        SELECT
            version_id, status, created_at, attempts, llm_latency_ms,
            llm_provider_used, llm_model_used,
            attempt_fail_reasons_json
        FROM oracle_task_versions
        WHERE llm_latency_ms IS NOT NULL
        ORDER BY llm_latency_ms DESC
        LIMIT 10
        """
    ).fetchall()
    for r in rows:
        print(
            _ts(r["created_at"]),
            r["version_id"],
            "lat_ms=",
            r["llm_latency_ms"],
            "attempts=",
            r["attempts"],
            "status=",
            r["status"],
            "model=",
            r["llm_provider_used"],
            r["llm_model_used"],
            "fail0=",
            _first_fail_reason(r["attempt_fail_reasons_json"]),
        )

    con.close()


if __name__ == "__main__":
    main()

