import type { RunResponse } from "../types/oracle";
import type { TelemetryEvent } from "./telemetry";

export type RunTestsIntegrationDeps = {
  oracleAsRunTests: boolean;
  oracleVersionId: string | null;
  runLocal: () => Promise<TelemetryEvent>;
  runOracle: (versionId: string) => Promise<RunResponse>;
  mapOracleRun: (run: RunResponse, ts: number) => TelemetryEvent;
  now?: () => number;
};

export async function getRunTestsTelemetryEvent(deps: RunTestsIntegrationDeps): Promise<{ event: TelemetryEvent; source: "local" | "oracle" }> {
  if (!deps.oracleAsRunTests) {
    return { event: await deps.runLocal(), source: "local" };
  }
  if (!deps.oracleVersionId) {
    throw new Error("oracle_version_id_missing");
  }
  const run = await deps.runOracle(deps.oracleVersionId);
  return {
    event: deps.mapOracleRun(run, deps.now ? deps.now() : Date.now()),
    source: "oracle",
  };
}
