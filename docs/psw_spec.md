# PSW Decision Layer Spec (Baseline)

## Definitions
- `S_i = pass_i / N`
- `S_best_i = max(S_best_{i-1}, S_i)`
- `Pabs_i = max(S_best_i - S_best_{i-1}, 0)`
- `theta = 1 / N` (cold-start)
- Significant progress: `Pabs_i >= theta`

## Chunk definition
- A chunk spans from the last significant progress event up to (but not including) the next significant progress event.

## Active time accounting
- `chunk_active_time` accumulates only when idle duration is **<= IDLE_CUTOFF**.
- Idle segments **> IDLE_CUTOFF** do not contribute to active time.
- `chunk_max_idle` stores the max continuous idle time seen within the chunk.

## Thresholds
- `T_ACTIVE` default = 120s.
- `SMALL_EDIT` default = 5 characters.

## Classification rules
- **In-PSW** if significant progress OR `chunk_active_time <= T_ACTIVE`.
- **Over-threshold** if `chunk_active_time > T_ACTIVE`, then:
  - **Flailing** if `chunk_runs >= FLAIL_RUNS` with no significant progress, or many small edits.
  - **Stalling** if `chunk_max_idle >= IDLE_CUTOFF` and `chunk_runs <= 1`, or low edits + long idle, or `run_gap >= RUN_GAP_SECONDS`.
  - If both match, **Flailing** takes priority.

## Sustain gating
- The “Need help?” badge appears only if Flailing or Stalling persists **continuously** for at least `SUSTAIN_SECONDS`.
- Any return to In-PSW resets the sustain timer.

## Replay case outputs (examples)
Case 1 (pass_count improves):
```
1000	In-PSW	S=0.00	S_best=0.00	active=0.0s	runs=1	max_idle=0.0s
2000	In-PSW	S=0.20	S_best=0.20	active=0.0s	runs=0	max_idle=0.0s
```

Case 2 (over threshold, runs>=3, no progress):
```
0	In-PSW	S=0.00	S_best=0.00	active=0.0s	runs=1	max_idle=0.0s
6000	In-PSW	S=0.00	S_best=0.00	active=6.0s	runs=2	max_idle=0.0s
12000	Flailing	S=0.00	S_best=0.00	active=12.0s	runs=3	max_idle=0.0s
```

Case 3 (over threshold, idle>=60, runs<=1):
```
0	In-PSW	S=0.00	S_best=0.00	active=0.0s	runs=0	max_idle=0.0s
12000	Stalling	S=0.00	S_best=0.00	active=12.0s	runs=0	max_idle=10.0s
13000	Stalling	S=0.00	S_best=0.00	active=12.0s	runs=0	max_idle=70.0s
```
