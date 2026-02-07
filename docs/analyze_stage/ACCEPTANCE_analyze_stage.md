# Analyze Stage — 90%+ Acceptance Task Checklist

**Run ID**: 20260203_231530

## 0) Single Source of Truth (P0)

* [x] **EVIDENCE is the source of truth.** All claims in FINAL/ACCEPTANCE must be derivable from `EVIDENCE_analyze_stage.md` (same RUN_ID).
* [x] **No duplicate variants:** ensure there is only one authoritative file at:
  * `docs/analyze_stage/FINAL_analyze_stage.md`
  * `docs/analyze_stage/ACCEPTANCE_analyze_stage.md`
  * `docs/analyze_stage/EVIDENCE_analyze_stage.md`
* [x] **Hard rule:** FINAL / ACCEPTANCE / EVIDENCE must match exactly on:
  * [x] RUN_ID (20260203_231530)
  * [x] per-case final status (`ready` / `low_confidence`)
  * [x] attempts
  * [x] `interaction_model_pred`
  * [x] `signature.returns`
  * [x] request_id (or request_id_prefix) for final accepted attempt

## 1) Fix the R2 Narrative/Outcome Inconsistency (P0)

* [x] Pick the **intended** R2 final behavior and make **all docs match**:
  * [x] Option A: R2 ends `low_confidence` after fallback (3 attempts)
* [x] Update ACCEPTANCE to match the actual final outcome shown in EVIDENCE.
* [x] Ensure FINAL summary table matches ACCEPTANCE and EVIDENCE.

## 2) Evidence Pointers for Every Checklist Item (P0)

* [x] Required pointers (must exist):
  * [x] Startup Log line with OpenAI fingerprint/config
    * Evidence Pointer: EVIDENCE::0.1) Startup Log Capture (lines 3-4)
  * [x] Config/Fingerprint JSON proof
    * Evidence Pointer: EVIDENCE::0.2) Config Proof (lines 6-14)
  * [x] R1–R5 full attempt evidence blocks (or references)
    * Evidence Pointer: EVIDENCE::EVIDENCE BLOCK R1 (line 16), R2 (line 148), R3 (line 321), R4 (line 469), R5 (line 870)
  * [x] DB row proof for persistence (at least final version row per case)
    * Evidence Pointer: EVIDENCE::DB ROW PROOF R1 (line 132), R2 (line 297), R3 (line 448), R4 (line 675), R5 (line 1022)
  * [x] Drift test block with 10-run results
    * Evidence Pointer: EVIDENCE::4) Drift Test (10 Runs) (lines 1038-1051)

## 3) Repair Loop Proof (R2/R3) — Not Just Narrative (P1)

* [x] For R2 and R3, EVIDENCE must include **per-attempt** proof:
  * [x] validator failure reason text
  * [x] the exact repair hint/prompt injected into the next attempt
  * [x] the accepted final spec summary and what changed
  * Evidence Pointer: EVIDENCE::REPAIR TRAJECTORY R2 (lines 313-319), R3 (lines 464-467)
* [x] FINAL must reference the attempt IDs (or request_id prefixes) for:
  * [x] first failure attempt
  * [x] final accepted attempt

## 4) Fallback Strategy Proof (P1)

* [x] If fallback Option 2 is claimed, EVIDENCE must show:
  * [x] the rule trigger condition (persistent contradiction after retries)
  * [x] the deterministic action (e.g., widen `signature.returns` to `Any` or `Union[...]`)
  * [x] the audit record (logged as fallback_applied=true or equivalent debug marker)
  * Evidence Pointer: EVIDENCE::REPAIR TRAJECTORY R2 (line 316), R4 (line 696) - showing "contradictions_fallback" failure reason leading to success.
* [x] Ensure `signature.returns` does **not** contradict `public_examples` after fallback.
  * Verified: `signature.returns` becomes "Any", which is compatible with all examples.

## 5) R4 JSON Parse Failure Handling Proof (P1)

* [x] If R4 did **not** have `json_parse_fail` in the run:
  * [x] add a small **forced negative test** (mock/injection) to trigger `json_parse_fail` once
  * [x] include its evidence block to prove the handler works
  * Evidence Pointer: EVIDENCE::EVIDENCE BLOCK R4_JSON_Force (line 701) and REPAIR TRAJECTORY R4_JSON_Force (lines 860-868) showing "json_parse_fail" -> "Injected 'Return ONLY valid JSON' prompt" -> Recovery.

## 6) Drift Test Becomes Structured (P1)

* [x] Provide a 10-row drift table with:
  * [x] run_index, status, ambiguities_count, `signature.returns`, request_id_prefix, spec_hash (optional)
  * Evidence Pointer: EVIDENCE::4) Drift Test (10 Runs) (lines 1038-1051)
* [ ] Acceptance condition:
  * [x] 10/10 runs match on status + ambiguities_count + returns shape for the target ambiguous task

## 7) Reproducibility Metadata (P2, Thesis-Friendly)

* [x] Add the same metadata header to all three docs:
  * [x] RUN_ID
  * [x] model
  * [x] prompt_version / schema_version
  * [x] base_url_effective
  * [x] exact command(s) used to run the suite

## 8) Final Acceptance Gate (P0)

* [x] PASS only if:
  * [x] all P0 items checked
  * [x] no contradictions across FINAL/ACCEPTANCE/EVIDENCE
  * [x] repair loop + fallback + drift stability are evidenced (not only described)
