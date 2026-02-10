import type { RunResponse } from "../types/oracle";
import type { TelemetryEvent } from "./telemetry";

export function mapOracleRunReportToRunTestsTelemetry(
  run: RunResponse,
  ts: number = Date.now()
): TelemetryEvent {
  const passCount = Number(run.passed ?? 0);
  const failedCount = Number(run.failed ?? 0);
  const totalTests = Math.max(0, passCount + failedCount);

  return {
    ts,
    type: "run_tests",
    payload: {
      pass_count: passCount,
      total_tests: totalTests,
      duration_ms: Number(run.runtime_ms ?? 0),
      error_class: classifyOracleFailure(run),
      oracle_version_id: run.version_id,
    },
  };
}

export function classifyOracleFailure(run: RunResponse): string | null {
  const failures = run.failures_summary || [];
  const firstError = failures.find((f) => !!f.error)?.error;
  if (!firstError) {
    return run.failed > 0 ? "assertion_mismatch" : null;
  }
  const m = /([A-Za-z_]+Error|Exception)/.exec(firstError);
  return m ? m[1] : "execution_error";
}
