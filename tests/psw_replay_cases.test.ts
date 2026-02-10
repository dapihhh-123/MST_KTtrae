import { describe, expect, it } from "vitest";
import { createPSWDetector } from "../src/psw/psw_detector";
import type { TelemetryEvent } from "../src/psw/telemetry";

const config = {
  IDLE_CUTOFF_SECONDS: 60,
  T_ACTIVE_SECONDS: 10,
  RUN_GAP_SECONDS: 90,
  FLAIL_RUNS: 3,
  MIN_CHAR_CHANGE: 20,
  MIN_EDIT_EVENTS: 12,
  SMALL_EDIT: 5,
  PSW_SUSTAIN_SECONDS: 20,
};

const ingestAll = (events: TelemetryEvent[]) => {
  const detector = createPSWDetector(config);
  let last = detector.ingest(events[0]);
  for (const evt of events.slice(1)) {
    last = detector.ingest(evt);
  }
  return last;
};

describe("PSW replay cases", () => {
  it("Case 1: pass_count improvement triggers significant progress and reset", () => {
    const events: TelemetryEvent[] = [
      { ts: 1000, type: "run_tests", payload: { pass_count: 0, total_tests: 5, duration_ms: 100 } },
      { ts: 2000, type: "run_tests", payload: { pass_count: 1, total_tests: 5, duration_ms: 100 } },
    ];

    const output = ingestAll(events);
    expect(output.state).toBe("In-PSW");
    expect(output.metrics.chunk_runs).toBe(0);
    expect(output.reason).toContain("significant_progress");
  });

  it("Case 2: over T_active with runs >= 3 and no progress => Flailing", () => {
    const events: TelemetryEvent[] = [
      { ts: 0, type: "run_tests", payload: { pass_count: 0, total_tests: 2, duration_ms: 100 } },
      { ts: 6000, type: "run_tests", payload: { pass_count: 0, total_tests: 2, duration_ms: 100 } },
      { ts: 12000, type: "run_tests", payload: { pass_count: 0, total_tests: 2, duration_ms: 100 } },
    ];

    const output = ingestAll(events);
    expect(output.state).toBe("Flailing");
    expect(output.reason).toContain("runs_without_progress");
    expect(output.reason).toContain("chunk_runs=3");
  });

  it("Case 3: over T_active with max_idle >= 60 and runs <= 1 => Stalling", () => {
    const events: TelemetryEvent[] = [
      { ts: 0, type: "edit", payload: { delta_chars: 5 } },
      { ts: 12000, type: "idle_heartbeat", payload: { idle_seconds_since_last_activity: 10 } },
      { ts: 13000, type: "idle_heartbeat", payload: { idle_seconds_since_last_activity: 70 } },
    ];

    const output = ingestAll(events);
    expect(output.state).toBe("Stalling");
    expect(output.reason).toContain("idle");
    expect(output.reason).toContain("chunk_max_idle");
  });
});
