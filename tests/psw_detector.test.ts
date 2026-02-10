import { describe, expect, it } from "vitest";
import { createPSWDetector } from "../src/psw/psw_detector";
import type { TelemetryEvent } from "../src/psw/telemetry";

const makeEvent = (overrides: Partial<TelemetryEvent>): TelemetryEvent => ({
  ts: overrides.ts ?? 0,
  type: overrides.type ?? "edit",
  payload: overrides.payload ?? {},
});

describe("PSWDetector", () => {
  it("treats pass_count improvement as significant progress and resets chunk", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 120,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    const output = detector.ingest(
      makeEvent({
        ts: 1000,
        type: "run_tests",
        payload: { pass_count: 1, total_tests: 5, duration_ms: 1200 },
      })
    );

    expect(output.metrics.S_best).toBeCloseTo(0.2);
    expect(output.metrics.chunk_runs).toBe(0);
    expect(output.state).toBe("In-PSW");
    expect(output.thresholds.theta).toBeCloseTo(0.2);
    expect(output.reason).toContain("significant_progress");
  });

  it("captures pre-reset metrics when significant progress occurs", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 120,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    detector.ingest(
      makeEvent({
        ts: 0,
        type: "run_tests",
        payload: { pass_count: 0, total_tests: 5, duration_ms: 1200 },
      })
    );

    const output = detector.ingest(
      makeEvent({
        ts: 1000,
        type: "run_tests",
        payload: { pass_count: 1, total_tests: 5, duration_ms: 1200 },
      })
    );

    expect(output.metrics.pre_chunk_runs).toBe(1);
    expect(output.metrics.chunk_runs).toBe(0);
    expect(output.reason).toContain("reset_chunk");
  });

  it("flags flailing when active time exceeds T and runs without progress", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 10,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    detector.ingest(makeEvent({ ts: 0, type: "run_tests", payload: { pass_count: 0, total_tests: 2, duration_ms: 1000 } }));
    detector.ingest(makeEvent({ ts: 6000, type: "run_tests", payload: { pass_count: 0, total_tests: 2, duration_ms: 1000 } }));
    const output = detector.ingest(
      makeEvent({ ts: 12000, type: "run_tests", payload: { pass_count: 0, total_tests: 2, duration_ms: 1000 } })
    );

    expect(output.metrics.chunk_active_time).toBeGreaterThan(10);
    expect(output.state).toBe("Flailing");
    expect(output.reason).toContain("runs_without_progress");
    expect(output.reason).toContain("chunk_runs=3");
  });

  it("flags stalling when active time exceeds T and max idle is high with few runs", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 10,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    detector.ingest(makeEvent({ ts: 0, type: "edit", payload: { delta_chars: 5 } }));
    detector.ingest(makeEvent({ ts: 12000, type: "idle_heartbeat", payload: { idle_seconds_since_last_activity: 10 } }));
    const output = detector.ingest(
      makeEvent({ ts: 13000, type: "idle_heartbeat", payload: { idle_seconds_since_last_activity: 70 } })
    );

    expect(output.metrics.chunk_active_time).toBeGreaterThan(10);
    expect(output.state).toBe("Stalling");
    expect(output.reason).toContain("idle");
    expect(output.reason).toContain("chunk_max_idle");
  });

  it("stays In-PSW when active time does not exceed threshold", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 120,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    const output = detector.ingest(makeEvent({ ts: 1000, type: "edit", payload: { delta_chars: 5 } }));
    expect(output.state).toBe("In-PSW");
    expect(output.reason).toContain("active_time");
  });

  it("treats total_tests <= 0 as safe default without progress", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 120,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    const output = detector.ingest(
      makeEvent({
        ts: 1000,
        type: "run_tests",
        payload: { pass_count: 1, total_tests: 0, duration_ms: 1200 },
      })
    );

    expect(output.metrics.S_best).toBe(0);
    expect(output.thresholds.theta).toBeNull();
    expect(output.state).toBe("In-PSW");
  });

  it("handles out-of-order timestamps safely", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 120,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    detector.ingest(makeEvent({ ts: 2000, type: "edit", payload: { delta_chars: 5 } }));
    const output = detector.ingest(makeEvent({ ts: 1000, type: "edit", payload: { delta_chars: 5 } }));
    expect(output.state).toBe("In-PSW");
    expect(output.reason).toBe("invalid_or_out_of_order_ts");
  });

  it("treats chunk_active_time equal to threshold as In-PSW", () => {
    const detector = createPSWDetector({
      IDLE_CUTOFF_SECONDS: 60,
      T_ACTIVE_SECONDS: 10,
      RUN_GAP_SECONDS: 90,
      FLAIL_RUNS: 3,
      MIN_CHAR_CHANGE: 20,
      MIN_EDIT_EVENTS: 12,
      SMALL_EDIT: 5,
      PSW_SUSTAIN_SECONDS: 20,
    });

    detector.ingest(makeEvent({ ts: 0, type: "edit", payload: { delta_chars: 5 } }));
    const output = detector.ingest(makeEvent({ ts: 10000, type: "edit", payload: { delta_chars: 5 } }));
    expect(output.metrics.chunk_active_time).toBe(10);
    expect(output.state).toBe("In-PSW");
  });
});
