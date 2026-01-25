export interface Session {
  id: string;
  created_at?: number;
  createdAt?: number;
  workspace_id?: string;
  title?: string;
}

export interface Thread {
  id: string;
  session_id: string;
  type: "global" | "breakout" | "topic" | "ai_write";
  title?: string;
  summary?: string;
  created_at?: number;
  createdAt?: number;
  anchor?: any;
}

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  thread_id?: string;
  threadId?: string;
  client_id?: string;
  clientId?: string;
  created_at?: number;
  createdAt?: number;
  meta?: any;
}

export interface Marker {
  id: string;
  session_id: string;
  thread_id: string;
  file: string;
  start_line: number;
  end_line: number;
  start_col?: number;
  end_col?: number;
  created_at: number;
}

export interface MarkerBrief {
  thread_id: string;
  line: number;
  title?: string;
}

export interface EventLog {
  id: string;
  session_id: string;
  type: string;
  payload: any;
  ts?: number;
}

export interface WSMessageEnvelope {
  type: WSEventType;
  session_id?: string;
  payload?: any;
  ts?: number;
  trace_id?: string;
  // Payload fields usually flattened in our backend
  state?: string;
  delta?: string;
  chunk?: string; // Add chunk alias for delta
  seq?: number;
  is_final?: boolean;
  thread_id?: string;
  message_id?: string;
  spans?: any[];
  ops?: any[];
  meta?: any;
}

// --- Enums ---

export enum HTTPEventType {
  COMPILE_ERROR = "compile_error",
  RUN_FAIL = "run_fail",
  TEST_FAIL = "test_fail",
  RUN_OK = "run_ok",
  TEST_OK = "test_ok",
  COMPILE = "compile",
  RUN = "run",
  TEST = "test"
}

export enum WSEventType {
  AI_STATE = "ai_state",
  AI_TEXT_CHUNK = "ai_text_chunk",
  HIGHLIGHT_SPANS = "highlight_spans",
  EDITOR_OPS = "editor_ops",
  NEW_MESSAGE = "new_message",
  THREAD_UPDATED = "thread_updated",
  MARKER_CREATED = "marker_created",
  MARKER_UPDATE = "marker_update"
}

// --- Editor Models ---
export interface Range {
  startLine: number;
  startCol: number;
  endLine: number;
  endCol: number;
}

export interface Position {
  line: number;
  col: number;
}

export interface BubbleState {
  text: string;
  loading?: boolean;
  type?: "error" | "info";
  emoji?: string;
}

export interface AIPresenceState {
  cursor?: Position | null;
  caret?: Position | null;
  selection?: Range | null;
  bubble?: BubbleState | null;
  loading: boolean;
  status?: "idle" | "thinking" | "writing" | "error" | "done";
}

export interface CodeSnapshot {
  content: string;
  id?: string;
  session_id?: string;
  cursor_line?: number;
  cursor_col?: number;
  created_at?: number;
}

export interface ConsoleEntry {
  id: string;
  kind: "log" | "error" | "info" | "stdout";
  text: string;
}

export type GlobalThread = TopicThread | BreakoutSummaryThread;

export interface TopicThread {
  id: string;
  kind: "topic";
  title: string;
  summary?: string;
  messages?: Message[];
  collapsed?: boolean;
  createdAt: number;
}

export interface BreakoutSummaryThread {
  id: string;
  kind: "breakoutSummary";
  title: string;
  summary: string;
  breakoutId: string;
  sourceMessageIds: string[];
  createdAt: number;
}

export interface Breakout {
  id: string;
  title: string;
  anchorStartLine: number;
  anchorEndLine: number;
  anchorFile?: string;
  open: boolean;
  position?: { x: number; y: number };
  summary?: string;
  messages: Message[];
}
