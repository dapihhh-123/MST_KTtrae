from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import models
from backend.utils import now
from backend.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, KEY_FINGERPRINT, DOTENV_PATH, ENV_LOADED # Added config imports
from backend.services.oracle.mock_llm import generate_spec as mock_generate_spec
from backend.services.oracle.mock_llm import generate_tests as mock_generate_tests
from backend.services.oracle.llm_oracle import generate_spec_with_llm, generate_tests_with_llm, OracleAnalyzeError
from backend.services.oracle.types import TaskSpec, GeneratedTests
from backend.services.oracle.utils import compute_bundle_hash, compute_initial_confidence, compute_post_tests_confidence, new_uuid, truncate_utf8_bytes
from backend.services.oracle.runner import default_resource_limits, default_sandbox_mode, load_code_text, run_cli_oracle, run_function_oracle


router = APIRouter(prefix="/oracle", tags=["oracle"])
logger = logging.getLogger("Backend")

# Startup log for Task Oracle
logger.info(f"[CFG] [ORACLE] OPENAI_KEY_PRESENT={KEY_FINGERPRINT['present']} OPENAI_KEY_PREFIX={KEY_FINGERPRINT['prefix']} OPENAI_KEY_SHA256_8={KEY_FINGERPRINT['sha256_8']} OPENAI_BASE_URL={OPENAI_BASE_URL} ENV_SOURCE={'dotenv' if ENV_LOADED else 'osenv'}")
logger.info(f"[CFG] [ORACLE] DOTENV_PATH_USED={DOTENV_PATH}")

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTaskBody(StrictModel):
    project_id: Optional[str] = None


class CreateTaskResp(StrictModel):
    task_id: str


class SpecBody(StrictModel):
    task_description: str
    language: str = "python"
    runtime: str = "python"
    deliverable_type: str = Field(default="function", pattern="^(function|cli|script)$")
    optional_interface_constraints: Optional[Dict[str, Any]] = None
    optional_nonfunctional_constraints: Optional[Dict[str, Any]] = None
    debug_invalid_mock: bool = False


class SpecResp(StrictModel):
    version_id: str
    spec_summary: Dict[str, Any]
    ambiguities: List[Dict[str, Any]]
    oracle_confidence_initial: float
    confidence_reasons: List[str]
    log_id: str


class ConfirmBody(StrictModel):
    selections: Dict[str, str]


class ConfirmResp(StrictModel):
    version_id: str
    status: str
    log_id: str


class GenerateTestsBody(StrictModel):
    public_examples_count: int = 5
    hidden_tests_count: int = 6
    difficulty_profile: Optional[Dict[str, Any]] = None
    debug_invalid_mock: bool = False


class GenerateTestsResp(StrictModel):
    version_id: str
    status: str
    oracle_confidence: float
    confidence_reasons: List[str]
    public_examples_preview: List[Dict[str, Any]]
    hidden_tests_count: int
    requested_hidden_tests_count: int
    generated_hidden_tests_count: int
    dropped_hidden_tests_count: int
    drop_reasons: List[str]
    hash: str
    seed: int
    log_id: str


class RunBody(StrictModel):
    entrypoint: Optional[str] = None
    code_snapshot_id: Optional[str] = None
    code_text: Optional[str] = None
    current_file_path: Optional[str] = None
    workspace_files: Optional[Dict[str, str]] = None
    timeout_sec: float = 2.5


class RunResp(StrictModel):
    run_id: str
    version_id: str
    pass_rate: float
    passed: int
    failed: int
    failures_summary: List[Dict[str, Any]]
    oracle_confidence_used: float
    runtime_ms: int
    sandbox_mode: str
    resource_limits: Dict[str, Any]
    log_id: str


def _get_task(db: Session, task_id: str) -> models.OracleTask:
    t = db.query(models.OracleTask).filter(models.OracleTask.task_id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="task_not_found")
    return t


def _get_version(db: Session, version_id: str) -> models.OracleTaskVersion:
    v = db.query(models.OracleTaskVersion).filter(models.OracleTaskVersion.version_id == version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="version_not_found")
    return v


def _next_version_number(db: Session, task_id: str) -> int:
    existing = db.query(models.OracleTaskVersion).filter(models.OracleTaskVersion.task_id == task_id).all()
    if not existing:
        return 1
    return max(int(v.version_number or 0) for v in existing) + 1


def _validate_confirmations(spec_json: Dict[str, Any], selections: Dict[str, str]) -> None:
    ambiguities = spec_json.get("ambiguities") or []
    if not ambiguities:
        return
    for amb in ambiguities:
        if not isinstance(amb, dict):
            continue
        amb_id = str(amb.get("ambiguity_id") or "")
        choices = amb.get("choices") or []
        valid = {str(c.get("choice_id")) for c in choices if isinstance(c, dict)}
        chosen = selections.get(amb_id)
        if amb_id and valid and chosen not in valid:
            raise HTTPException(status_code=400, detail=f"invalid_choice:{amb_id}")


def _requires_confirmation(ambiguities: Any) -> bool:
    return isinstance(ambiguities, list) and len(ambiguities) > 0


def _has_full_confirmations(*, ambiguities: Any, confirmations: Any) -> bool:
    if not _requires_confirmation(ambiguities):
        return True
    if not isinstance(confirmations, dict):
        return False
    sels = confirmations.get("selections")
    if not isinstance(sels, dict):
        return False
    needed = []
    for a in ambiguities:
        if isinstance(a, dict):
            aid = str(a.get("ambiguity_id") or "")
            if aid:
                needed.append(aid)
    return all(aid in sels for aid in needed)


def _schema_error_fields(e: ValidationError) -> List[str]:
    out: List[str] = []
    try:
        for err in e.errors():
            loc = err.get("loc") or ()
            if isinstance(loc, (list, tuple)) and loc:
                out.append(".".join(str(x) for x in loc))
    except Exception:
        out = []
    uniq: List[str] = []
    for x in out:
        if x not in uniq:
            uniq.append(x)
    return uniq


def _read_code_from_path(p: str) -> str:
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"cannot_read_file:{str(e)}")


@router.get("/debug/openai_key_fingerprint", response_model=Dict[str, Any])
def debug_openai_key_fingerprint() -> Dict[str, Any]:
    return {
        "key_present": KEY_FINGERPRINT["present"],
        "key_prefix": KEY_FINGERPRINT["prefix"],
        "key_sha256_8": KEY_FINGERPRINT["sha256_8"],
        "base_url_effective": OPENAI_BASE_URL,
        "loaded_from_dotenv": ENV_LOADED,
        "dotenv_path_used": str(DOTENV_PATH)
    }

@router.get("/debug/config", response_model=Dict[str, Any])
def debug_config() -> Dict[str, Any]:
    return {
        "openai_api_key_present": bool(OPENAI_API_KEY),
        "openai_base_url": OPENAI_BASE_URL,
        "openai_org": None,
        "openai_project": None,
        "use_mock_llm": False,
        "sandbox_mode": "local",
        "env_loaded_from_dotenv": True,
        "key_sha256_8": KEY_FINGERPRINT["sha256_8"] # Added for convenience
    }

@router.get("/debug/last_spec_call", response_model=Dict[str, Any])
def debug_last_spec_call(db: Session = Depends(get_db)) -> Dict[str, Any]:
    # Fetch the most recent task version
    v = db.query(models.OracleTaskVersion).order_by(models.OracleTaskVersion.created_at.desc()).first()
    if not v:
        return {"error": "no_calls_found"}
        
    # Get fail reasons to determine error type/message
    fail_reasons = v.attempt_fail_reasons_json or []
    last_error = fail_reasons[-1] if fail_reasons else None
    
    # Parse last error for structured info
    error_type = None
    error_message = None
    if v.status == "analyze_failed" and last_error:
        error_message = str(last_error)
        if ":" in error_message:
            error_type = error_message.split(":")[0].strip()
        else:
            error_type = "unknown_error"
    
    return {
        "ts": int(v.created_at or 0),
        "provider": v.llm_provider_used,
        "model": v.llm_model_used,
        "interaction_model_pred": v.interaction_model_pred,
        "endpoint": "chat.completions",
        "base_url_effective": OPENAI_BASE_URL,
        "request_ids": [v.spec_llm_request_id] if v.spec_llm_request_id else [],
        "latency_ms": v.llm_latency_ms,
        "attempts": v.attempts,
        "prompt_version": v.spec_prompt_version,
        "schema_version": v.schema_version,
        "status": v.status,
        "error_type": error_type,
        "error_message": error_message,
        "fail_reasons": fail_reasons # Full history
    }

@router.post("/task", response_model=CreateTaskResp)
def create_task(body: CreateTaskBody, db: Session = Depends(get_db)) -> Dict[str, Any]:
    task_id = new_uuid()
    t = models.OracleTask(task_id=task_id, project_id=body.project_id, created_at=now(), updated_at=now())
    db.add(t)
    db.commit()
    logger.info(f"[oracle] create_task task_id={task_id} project_id={body.project_id}")
    return {"task_id": task_id}


@router.post("/task/{task_id}/version/spec", response_model=SpecResp)
def create_spec(task_id: str, body: SpecBody, db: Session = Depends(get_db)) -> Dict[str, Any]:
    _get_task(db, task_id)
    version_id = new_uuid()
    ver_n = _next_version_number(db, task_id)

    if body.debug_invalid_mock:
        spec_json, spec_meta = mock_generate_spec(
            task_description=body.task_description,
            language=body.language,
            runtime=body.runtime,
            deliverable_type=body.deliverable_type,
            optional_interface_constraints=body.optional_interface_constraints,
            optional_nonfunctional_constraints=body.optional_nonfunctional_constraints,
            debug_invalid_mock=True,
        )
    else:
        try:
            spec_json, spec_meta = generate_spec_with_llm(
                task_description=body.task_description,
                language=body.language,
                runtime=body.runtime,
                deliverable_type=body.deliverable_type
            )
        except OracleAnalyzeError as e:
            # 3.2 Persist failure trace to DB
            meta = e.metadata
            v = models.OracleTaskVersion(
                version_id=version_id,
                task_id=task_id,
                version_number=ver_n,
                status="analyze_failed",
                created_at=now(),
                spec_json={},
                ambiguities_json=[],
                user_confirmations_json={},
                public_examples_json=[],
                hidden_tests_json=[],
                oracle_confidence=0.0,
                conflict_report_json={},
                seed=0,
                hash="",
                # Trace info
                spec_llm_raw_json=meta.get("raw_text"),
                llm_raw_spec_json=meta.get("raw_text"),
                llm_model_used=meta.get("llm_model_used"),
                llm_provider_used=meta.get("llm_provider_used"),
                spec_llm_request_id=meta.get("request_id"),
                llm_latency_ms=meta.get("llm_latency_ms"),
                attempts=meta.get("attempts"),
                attempt_fail_reasons_json=meta.get("attempt_fail_reasons"),
                missing_fields_json=meta.get("missing_fields")
            )
            db.add(v)
            db.commit()
            
            logger.info(f"[ANALYZE] version_id={version_id} provider=openai model={meta.get('llm_model_used')} attempts={meta.get('attempts')} status=analyze_failed latency_ms={meta.get('llm_latency_ms')} request_id={meta.get('request_id')} error_type=analyze_failed")

            raise HTTPException(status_code=422, detail={
                "error": "analyze_failed",
                "stage": "llm_call",
                "version_id": version_id,
                "attempts": meta.get("attempts"),
                "request_ids": [meta.get("request_id")] if meta.get("request_id") else [],
                "fail_reasons": [{"attempt": i+1, "message": r} for i, r in enumerate(meta.get("attempt_fail_reasons", []))]
            })

    logger.info(f"[ORACLE] Spec Meta: {spec_meta}")
    
    try:
        spec = TaskSpec.model_validate(spec_json)
    except ValidationError as e:
        log_id = new_uuid()
        fields = _schema_error_fields(e)
        logger.info(f"[oracle] create_spec schema_fail log_id={log_id} task_id={task_id} fields={fields}")
        raise HTTPException(status_code=422, detail={"error": "schema_validation_failed", "schema_error_fields": fields, "log_id": log_id})
    spec_json = spec.model_dump()

    # P5: Lightweight coverage check and patching
    desc_lower = body.task_description.lower()
    constraints = spec_json.get("constraints") or []
    
    # 0) Fallback Extraction for Empty Constraints
    # If constraints are empty but description implies rules, extract them deterministically.
    rule_keywords = ["规则", "要求", "rules", "requirements", "must", "should"]
    has_rules_text = any(k in desc_lower for k in rule_keywords)
    
    if len(constraints) == 0 and has_rules_text:
        import re
        extracted_rules = []
        # Match numbered lists: "1) ...", "1. ...", "- ..."
        # Simple regex for lines starting with number/bullet
        lines = body.task_description.split('\n')
        for line in lines:
            line = line.strip()
            # Regex: Start with digit+dot/paren or hyphen/star, then space
            if re.match(r'^(\d+[\.\)]|\-|\*)\s+', line):
                # Clean prefix
                content = re.sub(r'^(\d+[\.\)]|\-|\*)\s+', '', line).strip()
                if len(content) > 5: # Ignore too short noise
                    extracted_rules.append(content)
        
        if extracted_rules:
            constraints.extend(extracted_rules)
            # Add warning (non-blocking)
            current_assumptions = spec_json.get("assumptions") or []
            current_assumptions.append("[Internal] Constraints were auto-extracted from description due to LLM omission.")
            spec_json["assumptions"] = current_assumptions

    # 1) Sorting Requirement
    sorting_keywords = ["sorted", "ascending", "order by", "increasing", "排序", "从小到大", "升序", "按起点", "按 start"]
    if any(k in desc_lower for k in sorting_keywords):
        has_sorting = any("sort" in c.lower() or "order" in c.lower() or "排序" in c or "升序" in c for c in constraints)
        if not has_sorting:
            constraints.append("Return intervals sorted by start in ascending order.")

    # 2) Empty Input Behavior
    empty_keywords = ["empty", "no intervals", "为空", "空列表", "空输入", "没有任何区间"]
    if any(k in desc_lower for k in empty_keywords):
        has_empty_rule = any("empty" in c.lower() or "空" in c for c in constraints)
        if not has_empty_rule:
            constraints.append("If input is empty, return an empty list.")
            
    # 3) Interval Representation (fix hardcoded "list of lists")
    # Scan assumptions/constraints for "list of lists" and fix if user didn't explicitly ask for it
    user_asked_list = "list of lists" in desc_lower or "list[list" in desc_lower or "[[int" in desc_lower
    if not user_asked_list:
        for i, c in enumerate(constraints):
            if "list of lists" in c.lower():
                constraints[i] = c.replace("list of lists", "list of tuples or lists (pairs)")
        
        assumptions = spec_json.get("assumptions") or []
        for i, a in enumerate(assumptions):
            if "list of lists" in a.lower():
                assumptions[i] = a.replace("list of lists", "list of tuples or lists (pairs)")
        spec_json["assumptions"] = assumptions

    spec_json["constraints"] = constraints
    
    raw_ambiguities = spec_json.get("ambiguities") or []
    
    # 1) Filter internal warnings (auto-resolved or single-choice)
    user_facing_ambiguities = []
    internal_warnings = []
    
    for amb in raw_ambiguities:
        aid = amb.get("ambiguity_id")
        choices = amb.get("choices") or []
        
        # Rule: Internal auto-resolutions go to warnings
        if aid == "auto_resolved_contradiction":
            internal_warnings.append({"id": aid, "message": amb.get("question") or amb.get("description"), "severity": "info"})
            continue
            
        # Rule: Single-choice items are auto-confirmed (or skipped)
        if len(choices) <= 1:
            internal_warnings.append({"id": aid, "message": f"Auto-confirmed single choice: {amb.get('question') or amb.get('description')}", "severity": "info"})
            continue
            
        user_facing_ambiguities.append(amb)

    # 2) Re-assign filtered list to spec_json for storage
    # FIX: Map 'question' to 'description' for frontend compatibility
    for amb in user_facing_ambiguities:
        if "description" not in amb and "question" in amb:
            amb["description"] = amb["question"]
            
    spec_json["ambiguities"] = user_facing_ambiguities
    # Store warnings in assumptions temporarily if schema strict, or just log them
    if internal_warnings:
        # Append to assumptions so they are visible in debug but don't block
        current_assumptions = spec_json.get("assumptions") or []
        for w in internal_warnings:
            current_assumptions.append(f"[Internal] {w['message']}")
        spec_json["assumptions"] = current_assumptions

    conf0, conf_reasons0 = compute_initial_confidence(spec_json)
    
    # 4) Return-Type Consistency Guard (Post-Processing)
    # Detect if "return None" is implied but signature returns atomic type
    none_return_keywords = ["return none", "returns none", "none if", "返回 none", "返回空", "不存在则返回 none"]
    
    # Check constraints and assumptions for None-return signals
    all_rules_text = (constraints + (spec_json.get("assumptions") or []) + [desc_lower])
    
    requires_optional = False
    for text_item in all_rules_text:
        lower_item = text_item.lower()
        if any(k in lower_item for k in none_return_keywords):
            requires_optional = True
            break
            
    if requires_optional and spec.signature:
        current_ret = spec.signature.returns
        # Upgrade atomic types to Optional[T]
        atomic_types = ["str", "int", "bool", "float", "list", "dict", "set", "tuple"]
        if current_ret in atomic_types:
            new_ret = f"Optional[{current_ret}]"
            spec.signature.returns = new_ret
            spec_json["signature"]["returns"] = new_ret # Update json dict as well
            
            # Add internal warning/reason
            conf_reasons0.append("signature_return_upgraded_to_optional")
            # Cap confidence slightly to reflect the ambiguity correction
            conf0 = min(conf0, 0.85)
            
    status = "awaiting_confirmation" if len(user_facing_ambiguities) > 0 else "ready"
    
    # 5) Confidence floor for valid specs without user ambiguities
    status = "awaiting_confirmation" if len(user_facing_ambiguities) > 0 else "ready"
    
    # 5) Confidence floor for valid specs without user ambiguities
    if len(user_facing_ambiguities) == 0 and conf0 < 0.4:
        # Boost confidence slightly if no user action needed
        conf0 = max(conf0, 0.5) 
        
    if conf0 < 0.4:
        status = "low_confidence"

    seed = int(abs(hash(version_id)) % (2**31 - 1))
    public_examples_json = [e.model_dump() for e in spec.public_examples]
    hidden_tests_json: List[Dict[str, Any]] = []
    bundle_hash = compute_bundle_hash(spec_json=spec_json, public_examples_json=public_examples_json, hidden_tests_json=hidden_tests_json, seed=seed)

    v = models.OracleTaskVersion(
        version_id=version_id,
        task_id=task_id,
        version_number=ver_n,
        status=status,
        created_at=now(),
        spec_json=spec_json,
        ambiguities_json=user_facing_ambiguities,
        user_confirmations_json={},
        public_examples_json=public_examples_json,
        hidden_tests_json=hidden_tests_json,
        oracle_confidence=float(conf0),
        conflict_report_json={"confidence_reasons": conf_reasons0},
        seed=seed,
        hash=bundle_hash,
    )
    # Observability - assign after init to ensure it sticks
    v.spec_llm_raw_json = spec_meta.get("raw_text")
    v.llm_raw_spec_json = spec_meta.get("raw_text")
    v.spec_prompt_version = spec_meta.get("prompt_version")
    
    # Trace B1 - Map from llm_oracle metadata
    v.llm_model_used = spec_meta.get("llm_model_used")
    v.llm_provider_used = spec_meta.get("llm_provider_used")
    v.spec_llm_request_id = spec_meta.get("request_id")
    v.llm_latency_ms = spec_meta.get("llm_latency_ms")
    v.normalized_input_hash = spec_meta.get("normalized_input_hash")
    v.schema_version = spec_meta.get("schema_version")
    v.interaction_model_pred = spec_meta.get("interaction_model_pred")
    v.attempts = spec_meta.get("attempts")
    v.attempt_fail_reasons_json = spec_meta.get("attempt_fail_reasons")
    v.missing_fields_json = spec_meta.get("missing_fields")

    db.add(v)
    db.commit()

    # 3.3 Logs must reflect reality
    logger.info(f"[ANALYZE] version_id={version_id} provider={v.llm_provider_used} model={v.llm_model_used} attempts={v.attempts} status={status} latency_ms={v.llm_latency_ms} request_id={v.spec_llm_request_id}")

    log_id = new_uuid()
    logger.info(f"[oracle] create_spec log_id={log_id} task_id={task_id} version_id={version_id} status={status} conf0={conf0}")
    return {
        "version_id": version_id,
        "spec_summary": {
            "goal_one_liner": spec.goal_one_liner,
            "deliverable": spec.deliverable,
            "language": spec.language,
            "runtime": spec.runtime,
            "signature": spec.signature.model_dump() if spec.signature else None,
            "constraints": spec.constraints,
            "assumptions": spec.assumptions,
        },
        "ambiguities": user_facing_ambiguities,
        "oracle_confidence_initial": float(conf0),
        "confidence_reasons": conf_reasons0,
        "log_id": log_id,
    }


@router.post("/version/{version_id}/confirm", response_model=ConfirmResp)
def confirm_version(version_id: str, body: ConfirmBody, db: Session = Depends(get_db)) -> Dict[str, Any]:
    v = _get_version(db, version_id)
    spec_json = v.spec_json or {}
    ambiguities = v.ambiguities_json or (spec_json.get("ambiguities") if isinstance(spec_json, dict) else []) or []
    _validate_confirmations(spec_json, body.selections)
    if _requires_confirmation(ambiguities):
        for a in ambiguities:
            if isinstance(a, dict):
                aid = str(a.get("ambiguity_id") or "")
                if aid and aid not in body.selections:
                    raise HTTPException(status_code=400, detail=f"missing_confirmation:{aid}")
    v.user_confirmations_json = {"selections": dict(body.selections)}
    if v.status != "low_confidence":
        v.status = "ready"
        
    # Recalculate confidence now that ambiguities are resolved
    conf_new, reasons_new = compute_initial_confidence(spec_json, confirmations=v.user_confirmations_json)
    v.oracle_confidence = float(conf_new)
    
    # Update conflict report
    conflict_report = v.conflict_report_json or {}
    if isinstance(conflict_report, dict):
        conflict_report = dict(conflict_report)
    else:
        conflict_report = {}
    conflict_report["confidence_reasons"] = reasons_new
    v.conflict_report_json = conflict_report
        
    db.add(v)
    db.commit()
    log_id = new_uuid()
    logger.info(f"[oracle] confirm log_id={log_id} version_id={version_id} status={v.status} new_conf={v.oracle_confidence}")
    return {"version_id": version_id, "status": v.status, "log_id": log_id}


@router.post("/version/{version_id}/generate-tests", response_model=GenerateTestsResp)
def generate_tests(version_id: str, body: GenerateTestsBody, db: Session = Depends(get_db)) -> Dict[str, Any]:
    v = _get_version(db, version_id)
    spec_json = v.spec_json or {}
    ambiguities = v.ambiguities_json or []
    confirmations = v.user_confirmations_json or {}
    if not _has_full_confirmations(ambiguities=ambiguities, confirmations=confirmations):
        raise HTTPException(status_code=400, detail="ambiguities_not_confirmed")

    seed = int(v.seed or 0) or int(abs(hash(version_id)) % (2**31 - 1))
    
    if body.debug_invalid_mock:
        tests_json, tests_meta = mock_generate_tests(
            spec_json=spec_json,
            confirmations=confirmations if isinstance(confirmations, dict) else {},
            public_examples_count=int(body.public_examples_count),
            hidden_tests_count=int(body.hidden_tests_count),
            difficulty_profile=body.difficulty_profile,
            seed=seed,
            debug_invalid_mock=True,
        )
    else:
        tests_json, tests_meta = generate_tests_with_llm(
            spec_json=spec_json,
            confirmations=confirmations if isinstance(confirmations, dict) else {},
            public_examples_count=int(body.public_examples_count),
            hidden_tests_count=int(body.hidden_tests_count),
            difficulty_profile=body.difficulty_profile,
            seed=seed
        )

    try:
        bundle = GeneratedTests.model_validate(tests_json)
    except ValidationError as e:
        log_id = new_uuid()
        fields = _schema_error_fields(e)
        logger.info(f"[oracle] generate_tests schema_fail log_id={log_id} version_id={version_id} fields={fields}")
        raise HTTPException(status_code=422, detail={"error": "schema_validation_failed", "schema_error_fields": fields, "log_id": log_id})
    public_examples_json = [e.model_dump() for e in bundle.public_examples]

    requested_hidden = max(0, int(body.hidden_tests_count))
    raw_hidden = [t.model_dump() for t in bundle.hidden_tests]
    filtered: List[Dict[str, Any]] = []
    drop_reasons: List[str] = []
    seen_name: set[str] = set()
    for t in raw_hidden:
        if not isinstance(t, dict):
            drop_reasons.append("schema_fail")
            continue
        name = str(t.get("name") or "")
        if not name or name in seen_name:
            drop_reasons.append("duplicate")
            continue
        seen_name.add(name)
        filtered.append(t)
    if len(filtered) > requested_hidden:
        filtered = filtered[:requested_hidden]
        drop_reasons.append("cap")
    if len(filtered) < requested_hidden:
        drop_reasons.append("insufficient_candidates")
    uniq_reasons: List[str] = []
    for r in drop_reasons:
        if r not in uniq_reasons:
            uniq_reasons.append(r)
    dropped = max(0, requested_hidden - len(filtered))

    hidden_tests_json = filtered
    h = compute_bundle_hash(spec_json=spec_json, public_examples_json=public_examples_json, hidden_tests_json=hidden_tests_json, seed=seed)

    conf1, reasons1 = compute_post_tests_confidence(initial=float(v.oracle_confidence or 0.0), hidden_tests=hidden_tests_json)
    status = v.status
    if conf1 < 0.4:
        status = "low_confidence"
    elif status == "awaiting_confirmation":
        status = "ready"

    v.public_examples_json = public_examples_json
    v.hidden_tests_json = hidden_tests_json
    v.seed = seed
    v.hash = h
    v.oracle_confidence = float(conf1)
    conflict_report = v.conflict_report_json or {}
    if isinstance(conflict_report, dict):
        conflict_report = dict(conflict_report)
    else:
        conflict_report = {}
    conflict_report["confidence_reasons_post_tests"] = reasons1
    conflict_report["hidden_tests_drop_audit"] = {
        "requested_hidden_tests_count": int(requested_hidden),
        "generated_hidden_tests_count": int(len(hidden_tests_json)),
        "dropped_hidden_tests_count": int(dropped),
        "drop_reasons": uniq_reasons,
    }
    v.conflict_report_json = conflict_report
    v.status = status
    
    # Observability
    v.tests_llm_raw_json = tests_meta.get("raw_text")
    v.llm_raw_tests_json = tests_meta.get("raw_text")
    v.tests_prompt_version = tests_meta.get("prompt_version")
    
    db.add(v)
    db.commit()

    log_id = new_uuid()
    logger.info(f"[oracle] generate_tests log_id={log_id} version_id={version_id} status={v.status} conf={conf1} hidden={len(hidden_tests_json)}")
    return {
        "version_id": version_id,
        "status": v.status,
        "oracle_confidence": float(conf1),
        "confidence_reasons": reasons1,
        "public_examples_preview": public_examples_json,
        "hidden_tests_count": len(hidden_tests_json),
        "requested_hidden_tests_count": int(requested_hidden),
        "generated_hidden_tests_count": int(len(hidden_tests_json)),
        "dropped_hidden_tests_count": int(dropped),
        "drop_reasons": uniq_reasons,
        "hash": h,
        "seed": seed,
        "log_id": log_id,
    }


@router.post("/version/{version_id}/run", response_model=RunResp)
def run_oracle(version_id: str, body: RunBody, db: Session = Depends(get_db)) -> Dict[str, Any]:
    v = _get_version(db, version_id)
    spec_json = v.spec_json or {}
    spec = TaskSpec.model_validate(spec_json)

    code_text = load_code_text(db, code_snapshot_id=body.code_snapshot_id, code_text=body.code_text)
    if not code_text and body.current_file_path:
        code_text = _read_code_from_path(body.current_file_path)
    if not code_text:
        raise HTTPException(status_code=400, detail="missing_code")

    public_examples = v.public_examples_json or []
    hidden_tests = v.hidden_tests_json or []
    all_tests: List[Dict[str, Any]] = []
    for ex in public_examples:
        if isinstance(ex, dict):
            all_tests.append({"name": ex.get("name"), "input": ex.get("input"), "expected": ex.get("expected"), "hidden": False, "tags": []})
    for ht in hidden_tests:
        if isinstance(ht, dict):
            all_tests.append({"name": ht.get("name"), "input": ht.get("input"), "expected": ht.get("expected"), "hidden": True, "tags": ht.get("tags") or []})

    timeout_sec = float(body.timeout_sec or 2.5)
    stdout_max = 8 * 1024
    stderr_max = 8 * 1024
    sandbox_mode = default_sandbox_mode()
    limits = default_resource_limits(timeout_sec=timeout_sec)

    if spec.deliverable == "function":
        fn = body.entrypoint or (spec.signature.function_name if spec.signature else None)
        if not fn:
            raise HTTPException(status_code=400, detail="missing_entrypoint")
        exec_result = run_function_oracle(
            db=db,
            code_text=code_text,
            function_name=str(fn),
            tests=[{"name": t["name"], "input": t["input"], "expected": t["expected"]} for t in all_tests],
            timeout_sec=timeout_sec,
            stdout_max_bytes=stdout_max,
            stderr_max_bytes=stderr_max,
            sandbox_mode=sandbox_mode,
            resource_limits=limits,
            workspace_files=body.workspace_files,
            entrypoint=body.entrypoint,
        )
    else:
        exec_result = run_cli_oracle(
            code_text=code_text,
            tests=[{"name": t["name"], "input": t["input"], "expected": t["expected"]} for t in all_tests],
            timeout_sec_per_test=timeout_sec,
            stdout_max_bytes=stdout_max,
            stderr_max_bytes=stderr_max,
            sandbox_mode=sandbox_mode,
            resource_limits=limits,
            workspace_files=body.workspace_files,
            entrypoint=body.entrypoint,
        )

    parsed = exec_result.get("parsed") if isinstance(exec_result.get("parsed"), dict) else {}
    if bool(exec_result.get("timed_out")):
        passed = 0
        failed = max(1, len(all_tests))
        failures_full = [{"test_name": "__timeout__", "input": None, "expected": None, "got": None, "error": "TIMEOUT"}]
    elif exec_result.get("exit_code") == 137 or bool(exec_result.get("memory_exceeded")):
        passed = 0
        failed = max(1, len(all_tests))
        failures_full = [{"test_name": "__memory__", "input": None, "expected": None, "got": None, "error": "MEMORY_LIMIT"}]
    else:
        passed = int(parsed.get("passed") or 0)
        failed = int(parsed.get("failed") or 0)
        failures_full = parsed.get("failures") if isinstance(parsed.get("failures"), list) else []
        if passed == 0 and failed == 0 and len(all_tests) > 0:
            failed = len(all_tests)
            err_snip = truncate_utf8_bytes(str(exec_result.get("stderr") or ""), 512)
            failures_full = [{"test_name": "__runner_error__", "input": None, "expected": None, "got": None, "error": "RUNNER_PARSE_FAILED", "stderr": err_snip}]

    total = max(1, passed + failed)
    pass_rate = float(passed) / float(total)

    def _snip_value(v: Any, max_bytes: int) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return truncate_utf8_bytes(v, max_bytes)
        try:
            return truncate_utf8_bytes(json.dumps(v, ensure_ascii=False), max_bytes)
        except Exception:
            return truncate_utf8_bytes(str(v), max_bytes)

    def _snip_input(inp: Any, max_bytes: int) -> Any:
        if isinstance(inp, dict):
            out = dict(inp)
            stdin = out.get("stdin")
            if isinstance(stdin, str):
                out["stdin"] = truncate_utf8_bytes(stdin, max_bytes)
            return out
        if isinstance(inp, str):
            return truncate_utf8_bytes(inp, max_bytes)
        return inp

    leak_controlled: List[Dict[str, Any]] = []
    hidden_full_used = False
    for f in failures_full:
        if not isinstance(f, dict):
            continue
        name = str(f.get("test_name") or "")
        tmeta = next((t for t in all_tests if str(t.get("name") or "") == name), None)
        is_hidden = bool(tmeta.get("hidden")) if isinstance(tmeta, dict) else False
        tags = tmeta.get("tags") if isinstance(tmeta, dict) else []
        if not isinstance(tags, list):
            tags = []
        item: Dict[str, Any] = {"test_name": name, "tags": tags, "hidden": is_hidden}
        if is_hidden and not hidden_full_used:
            item["input"] = _snip_input(f.get("input"), 512)
            item["expected"] = _snip_value(f.get("expected"), 1024)
            item["got"] = _snip_value(f.get("got"), 1024)
            item["error"] = _snip_value(f.get("error"), 512) or None
            hidden_full_used = True
        elif is_hidden:
            item["error"] = f.get("error") or "hidden_test_failed"
        else:
            item["input"] = _snip_input(f.get("input"), 512)
            item["expected"] = _snip_value(f.get("expected"), 1024)
            item["got"] = _snip_value(f.get("got"), 1024)
            item["error"] = _snip_value(f.get("error"), 512) or None
        leak_controlled.append(item)
        if len(leak_controlled) >= 3:
            break

    run_id = new_uuid()
    stdout_t = truncate_utf8_bytes(str(exec_result.get("stdout") or ""), stdout_max)
    stderr_t = truncate_utf8_bytes(str(exec_result.get("stderr") or ""), stderr_max)
    r = models.OracleRun(
        run_id=run_id,
        version_id=version_id,
        created_at=now(),
        code_snapshot_id=body.code_snapshot_id,
        code_text=None if body.code_snapshot_id else code_text,
        pass_rate=float(pass_rate),
        passed=passed,
        failed=failed,
        failures_summary_json=leak_controlled,
        runtime_ms=int(exec_result.get("runtime_ms") or 0),
        memory_kb=int(exec_result.get("memory_kb") or 0),
        sandbox_mode=str(exec_result.get("sandbox_mode") or "local"),
        resource_limits_json=exec_result.get("resource_limits") if isinstance(exec_result.get("resource_limits"), dict) else {},
        stdout_trunc=stdout_t,
        stderr_trunc=stderr_t,
        sandbox_exit_code=exec_result.get("exit_code"),
    )
    db.add(r)
    db.commit()

    log_id = new_uuid()
    logger.info(f"[oracle] run log_id={log_id} run_id={run_id} version_id={version_id} pass_rate={pass_rate} passed={passed} failed={failed}")
    return {
        "run_id": run_id,
        "version_id": version_id,
        "pass_rate": float(pass_rate),
        "passed": passed,
        "failed": failed,
        "failures_summary": leak_controlled,
        "oracle_confidence_used": float(v.oracle_confidence or 0.0),
        "runtime_ms": int(exec_result.get("runtime_ms") or 0),
        "sandbox_mode": str(exec_result.get("sandbox_mode") or "local"),
        "resource_limits": exec_result.get("resource_limits") if isinstance(exec_result.get("resource_limits"), dict) else {},
        "log_id": log_id,
    }


@router.post("/task/{task_id}/version", response_model=Dict[str, Any])
def new_version(task_id: str, body: SpecBody, db: Session = Depends(get_db)) -> Dict[str, Any]:
    resp = create_spec(task_id, body, db)
    v = _get_version(db, resp["version_id"])
    return {"new_version_id": v.version_id, "version_number": int(v.version_number or 0)}


@router.get("/task/{task_id}", response_model=Dict[str, Any])
def get_task(task_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    t = _get_task(db, task_id)
    vers = db.query(models.OracleTaskVersion).filter(models.OracleTaskVersion.task_id == task_id).order_by(models.OracleTaskVersion.version_number.asc()).all()
    out = []
    for v in vers:
        hidden_tests = v.hidden_tests_json or []
        public_examples = v.public_examples_json or []
        out.append(
            {
                "version_id": v.version_id,
                "version_number": int(v.version_number or 0),
                "status": v.status,
                "created_at": float(v.created_at or 0.0),
                "oracle_confidence": float(v.oracle_confidence or 0.0),
                "public_examples_count": len(public_examples) if isinstance(public_examples, list) else 0,
                "hidden_tests_count": len(hidden_tests) if isinstance(hidden_tests, list) else 0,
                "hash": v.hash,
            }
        )
    return {"task_id": t.task_id, "versions": out}


@router.get("/version/{version_id}", response_model=Dict[str, Any])
def get_version(version_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    v = _get_version(db, version_id)
    spec_json = v.spec_json or {}
    spec = TaskSpec.model_validate(spec_json)
    hidden_tests = v.hidden_tests_json or []
    return {
        "spec_summary": {
            "goal_one_liner": spec.goal_one_liner,
            "deliverable": spec.deliverable,
            "language": spec.language,
            "runtime": spec.runtime,
            "signature": spec.signature.model_dump() if spec.signature else None,
            "constraints": spec.constraints,
            "assumptions": spec.assumptions,
        },
        "ambiguities": v.ambiguities_json or [],
        "confirmations": v.user_confirmations_json or {},
        "public_examples": v.public_examples_json or [],
        "hidden_tests_count": len(hidden_tests) if isinstance(hidden_tests, list) else 0,
        "oracle_confidence": float(v.oracle_confidence or 0.0),
        "conflict_report": v.conflict_report_json or {},
        "hash": v.hash,
        "seed": int(v.seed or 0),
        "status": v.status,
    }
