export type OracleStage = 
  | "init" 
  | "analyzing" 
  | "awaiting_confirmation" 
  | "ready_no_tests" 
  | "generating_tests" 
  | "tests_generated" 
  | "running" 
  | "run_done"
  | "low_confidence"
  | "error";

export interface CreateTaskResponse {
  task_id: string;
}

export interface SpecBody {
  task_description: string;
  language: string;
  deliverable_type: "function" | "cli" | "script";
  debug_invalid_mock: boolean;
}

export interface AmbiguityChoice {
  choice_id: string;
  text: string;
}

export interface Ambiguity {
  ambiguity_id: string;
  description: string;
  choices: AmbiguityChoice[];
}

export interface SpecSummary {
  goal_one_liner: string;
  constraints: string[];
  signature?: any;
  deliverable?: string;
  language?: string;
}

export interface GenerateSpecResponse {
  version_id: string;
  spec_summary: SpecSummary;
  ambiguities: Ambiguity[];
  oracle_confidence_initial: number;
  confidence_reasons: string[];
  log_id: string;
}

export interface ConfirmBody {
  selections: Record<string, string>;
}

export interface ConfirmResponse {
  version_id: string;
  status: string;
  log_id: string;
}

export interface GenerateTestsBody {
  public_examples_count: number;
  hidden_tests_count: number;
  difficulty_profile?: any;
}

export interface TestExample {
  input: any;
  expected: any;
  name?: string;
}

export interface GenerateTestsResponse {
  version_id: string;
  status: string;
  oracle_confidence: number;
  confidence_reasons: string[];
  public_examples_preview: TestExample[];
  hidden_tests_count: number;
  hash: string;
  log_id: string;
}

export interface RunBody {
  code_text?: string;
  code_snapshot_id?: string;
  timeout_sec: number;
  workspace_files?: Record<string, string>;
  entrypoint?: string;
}

export interface FailureItem {
  test_name: string;
  input: any;
  expected: any;
  got: any;
  error?: string;
  hidden: boolean;
}

export interface RunResponse {
  run_id: string;
  version_id: string;
  pass_rate: number;
  passed: number;
  failed: number;
  failures_summary: FailureItem[];
  oracle_confidence_used: number;
  runtime_ms: number;
  log_id: string;
}

export interface ApiLogEntry {
  ts: number;
  endpoint: string;
  durationMs: number;
  status: number | string;
  req: any;
  res: any;
}

export interface OracleVersion {
  versionId: string;
  createdAt: number;
  status?: string;
  confidence?: number;
  specSummary?: SpecSummary;
  publicExamples?: TestExample[];
  hiddenTestsCount?: number;
}
