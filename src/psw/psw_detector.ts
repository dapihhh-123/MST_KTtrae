import type { TelemetryEvent } from "./telemetry";
import type { PSWConfig } from "./config";

export type PSWState = "In-PSW" | "Flailing" | "Stalling";

export type PSWMetrics = {
  S: number;
  S_best: number;
  chunk_active_time: number;
  chunk_runs: number;
  chunk_max_idle: number;
  chunk_edit_chars: number;
  chunk_edit_events: number;
  chunk_small_edit_events: number;
  pre_chunk_active_time?: number | null;
  pre_chunk_runs?: number | null;
  pre_chunk_max_idle?: number | null;
  pre_chunk_edit_chars?: number | null;
  pre_chunk_small_edit_events?: number | null;
  last_run_ts: number | null;
  last_activity_ts: number | null;
};

export const PSW_VERSION = "1.0.0";

export type PSWThresholds = PSWConfig & {
  theta: number | null;
  total_tests: number | null;
  psw_version: string;
  config_hash: string;
};

export type PSWOutput = {
  state: PSWState;
  metrics: PSWMetrics;
  reason: string;
  thresholds: PSWThresholds;
};

type DetectorState = {
  lastEventTs: number | null;
  lastActivityTs: number | null;
  lastRunTs: number | null;
  chunkActiveSeconds: number;
  chunkRuns: number;
  chunkMaxIdleSeconds: number;
  chunkEditChars: number;
  chunkEditEvents: number;
  chunkSmallEditEvents: number;
  lastSigInfo: {
    pre_chunk_active_time: number;
    pre_chunk_runs: number;
    pre_chunk_max_idle: number;
    pre_chunk_edit_chars: number;
    pre_chunk_small_edit_events: number;
  } | null;
  S: number;
  SBest: number;
  lastPabs: number | null;
  lastTheta: number | null;
  lastTotalTests: number | null;
};

export class PSWDetector {
  private config: PSWConfig;
  private state: DetectorState;

  constructor(config: PSWConfig) {
    this.config = config;
    this.state = {
      lastEventTs: null,
      lastActivityTs: null,
      lastRunTs: null,
      chunkActiveSeconds: 0,
      chunkRuns: 0,
      chunkMaxIdleSeconds: 0,
      chunkEditChars: 0,
      chunkEditEvents: 0,
      chunkSmallEditEvents: 0,
      lastSigInfo: null,
      S: 0,
      SBest: 0,
      lastPabs: null,
      lastTheta: null,
      lastTotalTests: null,
    };
  }

  public ingest(event: TelemetryEvent): PSWOutput {
    const ok = this.advanceTime(event.ts, event.type, event.payload);
    if (!ok) {
      const metrics: PSWMetrics = {
        S: this.state.S,
        S_best: this.state.SBest,
        chunk_active_time: this.state.chunkActiveSeconds,
        chunk_runs: this.state.chunkRuns,
        chunk_max_idle: this.state.chunkMaxIdleSeconds,
        chunk_edit_chars: this.state.chunkEditChars,
        chunk_edit_events: this.state.chunkEditEvents,
        chunk_small_edit_events: this.state.chunkSmallEditEvents,
        last_run_ts: this.state.lastRunTs,
        last_activity_ts: this.state.lastActivityTs,
      };
      return {
        state: "In-PSW",
        metrics,
        reason: "invalid_or_out_of_order_ts",
        thresholds: {
          ...this.config,
          theta: this.state.lastTheta,
          total_tests: this.state.lastTotalTests,
          psw_version: PSW_VERSION,
          config_hash: configHash(this.config),
        },
      };
    }
    if (event.type === "run_tests") {
      this.applyRunTests(event);
    }
    if (event.type === "edit") {
      this.applyEdit(event);
    }
    if (event.type === "run_program") {
      this.state.lastActivityTs = event.ts;
    }
    if (event.type === "idle_heartbeat") {
      this.applyIdle(event);
    }

    const output = this.computeState();
    return output;
  }

  private advanceTime(ts: number, type: TelemetryEvent["type"], payload: TelemetryEvent["payload"]) {
    const lastTs = this.state.lastEventTs;
    if (!Number.isFinite(ts)) {
      return false;
    }
    if (lastTs !== null && ts < lastTs) {
      return false;
    }
    if (lastTs !== null && ts > lastTs) {
      const deltaSec = (ts - lastTs) / 1000;
      const idleSeconds = this.deriveIdleSeconds(type, payload);
      if (idleSeconds <= this.config.IDLE_CUTOFF_SECONDS) {
        this.state.chunkActiveSeconds += deltaSec;
      }
    }
    this.state.lastEventTs = ts;
    return true;
  }

  private deriveIdleSeconds(type: TelemetryEvent["type"], payload: TelemetryEvent["payload"]) {
    if (type === "idle_heartbeat") {
      const idle = Number(payload.idle_seconds_since_last_activity ?? 0);
      return Number.isFinite(idle) ? idle : 0;
    }
    return 0;
  }

  private applyRunTests(event: TelemetryEvent) {
    const pass = Number(event.payload.pass_count ?? 0);
    const total = Number(event.payload.total_tests ?? 0);
    if (!Number.isFinite(pass) || !Number.isFinite(total) || total <= 0) {
      this.state.S = 0;
      this.state.lastPabs = 0;
      this.state.lastTheta = null;
      this.state.lastTotalTests = null;
      this.state.lastRunTs = event.ts;
      this.state.lastActivityTs = event.ts;
      return;
    }
    const totalSafe = total;
    const S = pass / totalSafe;
    const prevBest = this.state.SBest;

    this.state.S = S;
    if (S > this.state.SBest) {
      this.state.SBest = S;
    }

    const theta = 1 / totalSafe;
    const Pabs = Math.max(this.state.SBest - prevBest, 0);
    this.state.lastPabs = Pabs;
    this.state.lastTheta = theta;
    this.state.lastTotalTests = totalSafe;
    if (Pabs >= theta) {
      this.state.lastSigInfo = {
        pre_chunk_active_time: this.state.chunkActiveSeconds,
        pre_chunk_runs: this.state.chunkRuns,
        pre_chunk_max_idle: this.state.chunkMaxIdleSeconds,
        pre_chunk_edit_chars: this.state.chunkEditChars,
        pre_chunk_small_edit_events: this.state.chunkSmallEditEvents,
      };
      this.resetChunk();
    } else {
      this.state.chunkRuns += 1;
    }

    this.state.lastRunTs = event.ts;
    this.state.lastActivityTs = event.ts;
  }

  private applyEdit(event: TelemetryEvent) {
    const delta = Number(event.payload.delta_chars ?? 0);
    if (Number.isFinite(delta)) {
      const absDelta = Math.abs(delta);
      this.state.chunkEditChars += absDelta;
      if (absDelta <= this.config.SMALL_EDIT) {
        this.state.chunkSmallEditEvents += 1;
      }
    }
    this.state.chunkEditEvents += 1;
    this.state.lastActivityTs = event.ts;
  }

  private applyIdle(event: TelemetryEvent) {
    const idle = Number(event.payload.idle_seconds_since_last_activity ?? 0);
    if (Number.isFinite(idle)) {
      this.state.chunkMaxIdleSeconds = Math.max(this.state.chunkMaxIdleSeconds, idle);
    }
  }

  private resetChunk() {
    this.state.chunkActiveSeconds = 0;
    this.state.chunkRuns = 0;
    this.state.chunkMaxIdleSeconds = 0;
    this.state.chunkEditChars = 0;
    this.state.chunkEditEvents = 0;
    this.state.chunkSmallEditEvents = 0;
  }

  private computeState(): PSWOutput {
    const metrics: PSWMetrics = {
      S: this.state.S,
      S_best: this.state.SBest,
      chunk_active_time: this.state.chunkActiveSeconds,
      chunk_runs: this.state.chunkRuns,
      chunk_max_idle: this.state.chunkMaxIdleSeconds,
      chunk_edit_chars: this.state.chunkEditChars,
      chunk_edit_events: this.state.chunkEditEvents,
      chunk_small_edit_events: this.state.chunkSmallEditEvents,
      pre_chunk_active_time: this.state.lastSigInfo?.pre_chunk_active_time ?? null,
      pre_chunk_runs: this.state.lastSigInfo?.pre_chunk_runs ?? null,
      pre_chunk_max_idle: this.state.lastSigInfo?.pre_chunk_max_idle ?? null,
      pre_chunk_edit_chars: this.state.lastSigInfo?.pre_chunk_edit_chars ?? null,
      pre_chunk_small_edit_events: this.state.lastSigInfo?.pre_chunk_small_edit_events ?? null,
      last_run_ts: this.state.lastRunTs,
      last_activity_ts: this.state.lastActivityTs,
    };
    const thresholds: PSWThresholds = {
      ...this.config,
      theta: this.state.lastTheta,
      total_tests: this.state.lastTotalTests,
      psw_version: PSW_VERSION,
      config_hash: configHash(this.config),
    };
    const runGapSeconds = metrics.last_run_ts ? Math.max(0, (this.state.lastEventTs ?? metrics.last_run_ts) - metrics.last_run_ts) / 1000 : null;
    const baseReason = `chunk_active_time=${metrics.chunk_active_time.toFixed(1)} ` +
      `chunk_runs=${metrics.chunk_runs} chunk_max_idle=${metrics.chunk_max_idle.toFixed(1)} ` +
      `run_gap=${runGapSeconds ?? "n/a"} ` +
      `small_edits=${metrics.chunk_small_edit_events} ` +
      `Pabs=${this.state.lastPabs ?? "n/a"} theta=${this.state.lastTheta ?? "n/a"} ` +
      `T_active=${this.config.T_ACTIVE_SECONDS}`;

    if (this.state.lastSigInfo) {
      this.state.lastSigInfo = null;
      return {
        state: "In-PSW",
        metrics,
        reason: `significant_progress(Pabs>=theta) sig_progress=true reset_chunk ${baseReason}`,
        thresholds,
      };
    }

    if (metrics.chunk_active_time <= this.config.T_ACTIVE_SECONDS) {
      return {
        state: "In-PSW",
        metrics,
        reason: `active_time_within_threshold ${baseReason}`,
        thresholds,
      };
    }

    const lowEdits = metrics.chunk_edit_chars < this.config.MIN_CHAR_CHANGE;
    const manySmallEdits = metrics.chunk_edit_events >= this.config.MIN_EDIT_EVENTS && lowEdits;
    const longIdle = metrics.chunk_max_idle >= this.config.IDLE_CUTOFF_SECONDS;
    const longNoRun = metrics.last_run_ts === null;
    const longRunGap = runGapSeconds !== null && runGapSeconds >= this.config.RUN_GAP_SECONDS;

    const flailing = metrics.chunk_runs >= this.config.FLAIL_RUNS && !longNoRun;
    const stalling = (longIdle && metrics.chunk_runs <= 1) || (lowEdits && longIdle) || longRunGap;

    if (flailing || manySmallEdits) {
      return {
        state: "Flailing",
        metrics,
        reason: `${flailing ? "runs_without_progress" : "many_small_edits_without_progress"} over_threshold=true ${baseReason}`,
        thresholds,
      };
    }

    if (stalling || (longNoRun && lowEdits)) {
      return {
        state: "Stalling",
        metrics,
        reason: `${stalling ? "idle_and_few_runs" : "no_runs_and_low_edits"} over_threshold=true ${baseReason}`,
        thresholds,
      };
    }

    return {
      state: "In-PSW",
      metrics,
      reason: `default_in_psw over_threshold=true ${baseReason}`,
      thresholds,
    };
  }
}

export function createPSWDetector(config: PSWConfig): PSWDetector {
  return new PSWDetector(config);
}

function configHash(config: PSWConfig): string {
  const sortedKeys = Object.keys(config).sort();
  const payload = sortedKeys.reduce<Record<string, number>>((acc, key) => {
    acc[key] = config[key as keyof PSWConfig] as number;
    return acc;
  }, {});
  return JSON.stringify(payload);
}
