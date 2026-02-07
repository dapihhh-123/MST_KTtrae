Below is a **copy-paste ready task checklist** for the **Validator Hardening gaps** (R2–R5 not executed due to connection errors, missing failure evidence blocks, missing PASS consistency proof, missing drift test).
Note: **your OpenAI key is stored in the project’s `.env` file**.

---

## Validator Hardening — Verification Task Checklist (R2–R5 + Drift + Consistency)

### 0) Environment & Config Proof (MUST)

* **任务描述（中文）**：启动服务并证明 OpenAI 配置来自 `.env`，且 `use_mock_llm=false`。
* Steps (EN):

  * Start backend in the same way as the previous successful runs.
  * Capture the **exact startup log line** containing OpenAI key fingerprint fields:

    * `OPENAI_KEY_PRESENT`, `OPENAI_KEY_PREFIX`, `OPENAI_KEY_SHA256_8`, `OPENAI_BASE_URL`, `ENV_SOURCE`, and the dotenv path used.
  * Call the config/fingerprint endpoint and capture the **full JSON**.

**Artifacts to paste (EN):**

* Startup log line(s) (exact)
* `GET /.../config` or `GET /.../fingerprint` JSON (full)

---

### 1) R2–R5 Real-LLM Regression (MUST — do not skip)

* **任务描述（中文）**：在真实 OpenAI 调用下重新跑通 R2、R3、R4、R5，确保不再因为连接错误而缺失证据。
* Steps (EN):

  * For each case **R2, R3, R4, R5**:

    1. Send the **Analyze request** (paste exact request JSON).
    2. Capture the **Analyze response JSON (full)**.
    3. Fetch **`GET /oracle/version/{version_id}` JSON (full)**.
    4. Immediately fetch **`GET /oracle/debug/last_spec_call` JSON (full)**.
    5. Query DB for that `version_id` and paste the **raw row JSON** (full).
    6. Add a one-line evaluation:

       * `interaction_model_match` (expected: cli → `cli_stdio`, ops → `stateful_ops`)
       * `ambiguity_check` (if prompt requires ambiguity, ambiguities must exist)
       * `confidence_reasonable` (`ready=0.9`, `low_confidence=0.3`)
       * `validator_result` should be **PASS** for valid cases

**Evidence block format (EN):**

* Use the same “EVIDENCE BLOCK Rx” structure you used previously.
* End each block with: `EVIDENCE_BLOCK_COMPLETE=true`

---

### 2) If Any R2–R5 Still Fail: Connection Error Evidence Blocks (MUST)

* **任务描述（中文）**：如果 R2–R5 仍出现连接失败，不允许只写“网络波动”，必须给出可验收的失败证据块。
* Steps (EN):

  * For each failed case:

    * Paste backend logs showing the **exact exception** (timeout/DNS/TLS/429/5xx/connection reset).
    * Paste **`/oracle/debug/last_spec_call` JSON** showing `status`, `error_type`, `error_message`, `attempts`.
    * Paste **DB row proof** (must include `attempts`, `attempt_fail_reasons_json`, `spec_llm_request_id` if present).
    * Make it explicit whether the failure occurred at `llm_call` stage or another stage.

---

### 3) PASS Case Consistency Check (MUST)

* **任务描述（中文）**：用一个成功用例（建议 R1）证明 debug 与 DB 持久化字段完全一致。
* Steps (EN):

  * Pick one PASS case (prefer R1).
  * Paste:

    * `GET /oracle/debug/last_spec_call` JSON
    * DB row JSON for the same `version_id`
  * Add a short comparison line proving these match:

    * `interaction_model_pred`
    * `attempts`
    * `llm_latency_ms`
    * `spec_llm_request_id`
    * `prompt_version` / `schema_version`

---

### 4) Drift Test (10 Runs) — Stability of Low Confidence + Triggers (MUST)

* **任务描述（中文）**：选择一个“必触发歧义”的任务（例如 output_format 或输入格式双支持），连续跑 10 次，证明稳定性。
* Steps (EN):

  * Select one ambiguity-triggering prompt (e.g., “return list vs string”).
  * Run Analyze **10 times** with the same request body.
  * Record a summary table with:

    * run_index
    * status (should be `low_confidence` every time)
    * ambiguities_count (should be ≥ 1 every time)
    * `signature.returns` (should be `Any` or `Union[...]` if output format is ambiguous)
    * `interaction_model_pred` (should be consistent, e.g., `stateful_ops`)
    * request_id_prefix
  * If any run returns `ready` or lacks ambiguity, flag it as a failure.

---

### 5) Final Summary Table (MUST)

* **任务描述（中文）**：汇总所有结果（R1–R5 + N1–N3 + drift test），给出最终可验收结论。
* Steps (EN):

  * Produce a final summary table containing at least:

    * case_id
    * status
    * ambiguities_count
    * interaction_model_pred
    * request_id_prefix
    * validator_result (PASS/FAIL + reason)
    * persistence_ok (yes/no)
    * notes

---

