# Codellaborator PSW Telemetry + Replay

## PSW Recording & Replay

### Record a session (telemetry JSONL)
1. Start the backend and frontend as usual.
2. Open a session in the UI (a `session_id` is created/loaded automatically).
3. Interact with the editor, run tests, or stay idle.
4. Telemetry is appended to:
   - `telemetry/<session_id>.jsonl`

You can also download the JSONL via:
- `GET /api/telemetry/<session_id>/download`

### Replay PSW state changes
Replay a recorded telemetry file and print the PSW state sequence:

```bash
python tools/replay_psw.py telemetry/<session_id>.jsonl
```

To adjust thresholds, pass a JSON config file:

```bash
python tools/replay_psw.py telemetry/<session_id>.jsonl --config path/to/psw_config.json
```

### View PSW status in the UI
- The top bar shows `PSW: In-PSW | Flailing | Stalling` in real time.
- If PSW is `Flailing` or `Stalling` for >= 20s, a **Need help?** badge appears.
- Clicking the badge opens a small placeholder help panel (no content yet).

## Acceptance self-check
- ✅ Pass at least one test => PSW indicator returns to `In-PSW`.
- ✅ 2+ minutes without significant progress + frequent test runs => `Flailing` + badge.
- ✅ 2+ minutes without significant progress + long idle => `Stalling` + badge.

## Algorithm spec (summary)
Definitions:
- `S = pass_count / total_tests` (guard: total_tests <= 0 -> 1)
- `S_best = max(S_best, S)` across chunks
- `Pabs = max(S_best_i - S_best_{i-1}, 0)`
- `theta = 1 / total_tests`
- `Sig_i = (Pabs >= theta)` → immediate chunk reset, state = `In-PSW`
- `chunk_active_time` accumulates only when idle <= `IDLE_CUTOFF_SECONDS`
- `T_active` is the active-time threshold (default 120s)

Classification (after `chunk_active_time > T_active`):
- **Flailing**: `chunk_runs >= FLAIL_RUNS` with no significant progress, or many small edits.
- **Stalling**: `chunk_max_idle >= IDLE_CUTOFF_SECONDS` with `chunk_runs <= 1`, or low edits + long idle, or `run_gap >= RUN_GAP_SECONDS`.
- If both match, Flailing takes priority.

All thresholds live in `src/psw/config.ts` and are echoed in PSW output.

## Spec baseline & test config
- Full baseline spec: `docs/psw_spec.md`
- Fixed test config: `psw/test_config.json`

## Oracle -> PSW run_tests adapter (feature flagged)
- Flag: `VITE_ORACLE_AS_RUN_TESTS`
- Default: `false` (OFF)
- OFF behavior: IDE `TEST` button keeps current local `testCode` flow unchanged.
- ON behavior: IDE `TEST` button uses Oracle Run (existing API) and maps run report to PSW `run_tests` telemetry via adapter.
- Oracle context source: selected Oracle `currentVersionId` is mirrored to localStorage key `psw_oracle_version_id` by Oracle panel.

### Rollback
Set `VITE_ORACLE_AS_RUN_TESTS=false` (or unset it) and reload frontend. This restores the original local test path.
