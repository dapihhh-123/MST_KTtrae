import { describe, expect, it, vi } from "vitest";
import { mapOracleRunReportToRunTestsTelemetry, classifyOracleFailure } from "../src/psw/oracle_run_adapter";
import { getRunTestsTelemetryEvent } from "../src/psw/run_tests_integration";
import type { RunResponse } from "../src/types/oracle";

const sampleRun: RunResponse = {
  run_id: "run_1",
  version_id: "ver_1",
  pass_rate: 0.5,
  passed: 2,
  failed: 2,
  failures_summary: [{ test_name: "t3", input: null, expected: null, got: null, error: "ValueError: bad", hidden: false }],
  oracle_confidence_used: 0.7,
  runtime_ms: 333,
  log_id: "log_1",
};

describe("oracle_run_adapter", () => {
  it("maps Oracle run report to run_tests telemetry", () => {
    const evt = mapOracleRunReportToRunTestsTelemetry(sampleRun, 1234);
    expect(evt.ts).toBe(1234);
    expect(evt.type).toBe("run_tests");
    expect(evt.payload).toMatchObject({
      pass_count: 2,
      total_tests: 4,
      duration_ms: 333,
      oracle_version_id: "ver_1",
      error_class: "ValueError",
    });
  });

  it("classifies non-error failures as assertion_mismatch", () => {
    expect(classifyOracleFailure({ ...sampleRun, failed: 1, failures_summary: [{ test_name: "x", input: 1, expected: 2, got: 1, hidden: false }] })).toBe("assertion_mismatch");
  });
});

describe("run_tests integration routing", () => {
  it("uses local path when oracle flag is off", async () => {
    const runLocal = vi.fn().mockResolvedValue({ ts: 1, type: "run_tests", payload: { pass_count: 1, total_tests: 1, duration_ms: 1 } });
    const runOracle = vi.fn().mockResolvedValue(sampleRun);
    const out = await getRunTestsTelemetryEvent({
      oracleAsRunTests: false,
      oracleVersionId: "ver_1",
      runLocal,
      runOracle,
      mapOracleRun: mapOracleRunReportToRunTestsTelemetry,
      now: () => 9,
    });
    expect(out.source).toBe("local");
    expect(runLocal).toHaveBeenCalledTimes(1);
    expect(runOracle).not.toHaveBeenCalled();
  });

  it("uses oracle path when oracle flag is on", async () => {
    const runLocal = vi.fn();
    const runOracle = vi.fn().mockResolvedValue(sampleRun);
    const out = await getRunTestsTelemetryEvent({
      oracleAsRunTests: true,
      oracleVersionId: "ver_1",
      runLocal,
      runOracle,
      mapOracleRun: mapOracleRunReportToRunTestsTelemetry,
      now: () => 10,
    });
    expect(out.source).toBe("oracle");
    expect(runOracle).toHaveBeenCalledWith("ver_1");
    expect(out.event.type).toBe("run_tests");
    expect((out.event.payload as any).total_tests).toBe(4);
  });
});
