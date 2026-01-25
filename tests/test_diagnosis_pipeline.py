import pytest
from unittest.mock import MagicMock, patch
from backend.services.pedagogical_classifier import PedagogicalClassifier
from backend.services.diagnostic_context import DiagnosticContextBuilder
from backend.services.diagnosis_pipeline import DiagnosisPipeline
from backend import models, schemas
import json

def test_pedagogical_classifier_compile():
    classifier = PedagogicalClassifier()
    
    # Test RECALL
    res = classifier.classify("COMPILE", "NameError: name 'x' is not defined", {})
    assert res["err_type_pedagogical"] == "RECALL"
    assert res["confidence"] == 0.8
    assert res["rule_id"] == "rule_compile_recall"
    
    # Test ADJUSTMENT
    res = classifier.classify("COMPILE", "SyntaxError: invalid syntax", {})
    assert res["err_type_pedagogical"] == "ADJUSTMENT"
    assert res["confidence"] == 0.8
    assert res["rule_id"] == "rule_compile_adjustment"

def test_pedagogical_classifier_logic():
    classifier = PedagogicalClassifier()
    
    # Test MODIFICATION (default logic)
    res = classifier.classify("LOGIC", "", {"total_changes": 5}, "Test failed: 1 != 2")
    assert res["err_type_pedagogical"] == "MODIFICATION"
    assert res["confidence"] == 0.5
    
    # Test DECOMPOSITION (large changes)
    res = classifier.classify("LOGIC", "", {"total_changes": 100}, "Test failed")
    assert res["err_type_pedagogical"] == "DECOMPOSITION"
    assert res["confidence"] == 0.6

def test_diagnostic_context_diff():
    # Mock DB
    db = MagicMock()
    builder = DiagnosticContextBuilder(db)
    
    old_code = "def foo():\n    return 1"
    new_code = "def foo():\n    return 2"
    
    diff = builder._compute_diff_summary(old_code, new_code)
    assert diff["added_lines"] == 1
    assert diff["removed_lines"] == 1

def test_resolve_thread_id():
    db = MagicMock()
    pipeline = DiagnosisPipeline(db)
    
    # 1. Payload
    assert pipeline.resolve_thread_id("sess", {"thread_id": "t1"}) == "t1"
    
    # 2. Marker
    db.query.return_value.filter.return_value.first.return_value = MagicMock(thread_id="t2")
    assert pipeline.resolve_thread_id("sess", {"marker_id": "m1"}) == "t2"
    
    # 3. Default (General)
    # Reset mock for general thread query
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id="t_gen")
    assert pipeline.resolve_thread_id("sess", {}) == "t_gen"

# Integration-like test for Schema
def test_diagnosis_result_schema():
    evidence = schemas.DiagnosisEvidence(
        spans=[],
        error_summary="err",
        error_hash="abc",
        natural_language="nl"
    )
    res = schemas.DiagnosisResult(
        session_id="sess",
        event_id="evt",
        thread_id="t1",
        err_type_coarse="COMPILE",
        err_type_pedagogical="RECALL",
        confidence=0.9,
        evidence=evidence,
        recommendations=[],
        debug={"psw_state": "idle"}
    )
    assert res.session_id == "sess"
    assert res.thread_id == "t1"
    assert res.evidence.error_summary == "err"
    assert res.evidence.error_hash == "abc"
    assert res.debug["psw_state"] == "idle"
