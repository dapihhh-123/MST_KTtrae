import type { Range, AIPresenceState, ConsoleEntry, Message } from "./types";

// --- Client Events (Sent to Backend) ---

export type ClientEvent =
  | { type: "GLOBAL_MESSAGE"; threadId: string; text: string; code: string }
  | { type: "BREAKOUT_MESSAGE"; breakoutId: string; text: string; code: string }
  | { type: "RUN"; code: string };

// --- Agent Actions (Received from Backend) ---

export type AgentResponse = {
  requestId: string;
  actions: AgentAction[];
};

export type AgentAction =
  | { type: "WAIT"; ms: number }
  
  // AI Presence
  | { type: "AI_SET_PRESENCE"; presence: Partial<AIPresenceState> }
  
  // Editor
  | { type: "EDITOR_REVEAL_LINE"; line: number }
  | { type: "EDITOR_SET_SELECTION"; range: Range }
  | { type: "EDITOR_DELETE"; range: Range }
  | { type: "EDITOR_INSERT"; range: Range; text: string; typing?: boolean; speedMs?: number; provenance?: boolean }
  | { type: "EDITOR_REPLACE"; range: Range; text: string; typing?: boolean; speedMs?: number; provenance?: boolean }
  
  // UI / State
  | { type: "THREAD_APPEND_MESSAGE"; threadId: string; message: Message }
  | { type: "BREAKOUT_APPEND_MESSAGE"; breakoutId: string; message: Message }
  | { type: "BREAKOUT_SET_OPEN"; breakoutId: string; open: boolean }
  | { type: "CONSOLE_APPEND"; entries: ConsoleEntry[] }
  | { type: "CONSOLE_CLEAR" };

export type UIAction =
  | { type: "SET_CODE"; code: string }
  | { type: "SET_CHAT_COLLAPSED"; collapsed: boolean }
  | { type: "THREAD_ADD"; thread: any }
  | { type: "THREAD_TOGGLE"; threadId: string }
  | { type: "THREAD_APPEND_MESSAGE"; threadId: string; message: any }
  | { type: "THREAD_SET_SUMMARY"; threadId: string; summary: string }
  | { type: "BREAKOUT_ADD"; breakout: any }
  | { type: "BREAKOUT_SET_ACTIVE"; breakoutId: string | null }
  | { type: "BREAKOUT_SET_OPEN"; breakoutId: string; open: boolean }
  | { type: "BREAKOUT_SET_POSITION"; breakoutId: string; position: { x: number; y: number } }
  | { type: "BREAKOUT_SET_SUMMARY"; breakoutId: string; summary: string }
  | { type: "BREAKOUT_APPEND_MESSAGE"; breakoutId: string; message: any }
  | { type: "THREAD_UPDATE_MESSAGE"; threadId: string; messageId: string; patch: any }
  | { type: "BREAKOUT_UPDATE_MESSAGE"; breakoutId: string; messageId: string; patch: any }
  | { type: "THREAD_UPSERT_MESSAGE"; threadId: string; message: any }
  | { type: "BREAKOUT_UPSERT_MESSAGE"; breakoutId: string; message: any }
  | { type: "AI_STREAM_CHUNK"; threadId: string; messageId: string; chunk: string }
  | { type: "CONSOLE_APPEND"; entries: any[] }
  | { type: "CONSOLE_CLEAR" }
  | { type: "SET_THREADS"; threads: any[] }
  | { type: "AI_SET_PRESENCE"; presence: Partial<AIPresenceState> }
  | { type: "HIGHLIGHT_SET"; spans: any[]; ttlMs?: number; traceId?: string }
  | { type: "EDITOR_OPS_SET"; ops: any[]; traceId?: string }
  | { type: "DIAGNOSIS_SET"; diagnosis: any; traceId?: string }
  | { type: "INTERVENTION_SET"; plan: any; traceId?: string }
  | { type: "SET_MARKERS"; markers: any[] };
