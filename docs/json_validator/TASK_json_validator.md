# Task: JSON Validator Enhancement

## Goal
Enhance the Oracle's JSON Spec generation to include strict validation, retry logic, and ambiguity detection.

## Sub-tasks
1. **Validator Logic**: Implement `validate_spec_structure` to check for missing fields, schema violations, and logic contradictions.
2. **Negative Tests (N1-N3)**: Create tests to verify the validator catches errors.
3. **Regression Tests (R1-R5)**: Verify existing functionality (Basic, CLI, Ops) still works or fails gracefully.
4. **Drift Test**: Verify stability over multiple runs.
5. **Persistence**: Store failure reasons in DB.

## Deliverables
- Updated `llm_oracle.py`
- Verification Scripts (`final_verification.py`, `run_validator_tests.py`)
- Evidence Package (docs/json_validator/*)
