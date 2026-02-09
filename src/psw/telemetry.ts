export type TelemetryEventType = "edit" | "run_tests" | "run_program" | "idle_heartbeat";

export type TelemetryEvent = {
  ts: number;
  type: TelemetryEventType;
  payload: Record<string, unknown>;
};

export type TelemetryEditPayload = {
  delta_chars: number;
  cursor_line: number | null;
  file_id?: string;
};

export type TelemetryRunTestsPayload = {
  pass_count: number;
  total_tests: number;
  error_class?: string | null;
  duration_ms: number;
};

export type TelemetryIdlePayload = {
  idle_seconds_since_last_activity: number;
};

export const telemetryExample: TelemetryEvent = {
  ts: 1710000000000,
  type: "edit",
  payload: {
    delta_chars: 12,
    cursor_line: 42,
    file_id: "main.py",
  },
};
