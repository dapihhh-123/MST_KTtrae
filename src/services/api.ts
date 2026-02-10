import { getSessionId, initSession } from "./session";
import type { CodeSnapshot, Message, MarkerBrief, Session, Thread } from "../types";
import type { 
    ApiLogEntry, CreateTaskResponse, GenerateSpecResponse, SpecBody, 
    ConfirmBody, ConfirmResponse, GenerateTestsBody, GenerateTestsResponse,
    RunBody, RunResponse
} from "../types/oracle";

const BASE_URL = (() => {
  const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined;
  if (envBase && typeof envBase === "string" && envBase.length > 0) return envBase.endsWith("/") ? envBase.slice(0, -1) : envBase;
  const host = typeof window !== "undefined" ? window.location.hostname : "";
  if (host && host !== "localhost" && host !== "127.0.0.1") return "http://127.0.0.1:8000/api";
  return "/api";
})();

export type ApiLogger = (entry: ApiLogEntry) => void;
let globalApiLogger: ApiLogger | null = null;

export function setApiLogger(logger: ApiLogger | null) {
  globalApiLogger = logger;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const start = Date.now();
  const sessionId = getSessionId();
  if (!sessionId) {
      throw new Error("Session ID not found. Call initSession() first.");
  }
  
  // Replace {session_id} in endpoint
  const url = `${BASE_URL}${endpoint.replace("{session_id}", sessionId)}`;
  
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  
  if (sessionId) {
      headers["x-session-id"] = sessionId;
  }

  let resBody: any = null;
  let status: number | string = "pending";
  let reqBody = options.body ? JSON.parse(options.body as string) : undefined;

  try {
    const response = await fetch(url, { ...options, headers });
    status = response.status;
    
    if (!response.ok) {
      const errorText = await response.text();
      try {
          resBody = JSON.parse(errorText);
      } catch {
          resBody = { error: errorText };
      }
      throw new Error(`API Error ${response.status}: ${errorText}`);
    }
    
    resBody = await response.json();
    return resBody;
  } catch (e: any) {
    status = e.message || "error";
    resBody = { error: String(e) };
    throw e;
  } finally {
    if (globalApiLogger) {
        globalApiLogger({
            ts: Date.now(),
            endpoint,
            durationMs: Date.now() - start,
            status,
            req: reqBody,
            res: resBody
        });
    }
  }
}

async function requestWithSessionQuery<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const sessionId = getSessionId();
  if (!sessionId) {
    throw new Error("Session ID not found. Call initSession() first.");
  }
  const url = `${BASE_URL}${endpoint}${endpoint.includes("?") ? "&" : "?"}session_id=${encodeURIComponent(sessionId)}`;
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json();
}

export const api = {
  // Session
  getSessionId: getSessionId,
  initSession: initSession,

  // Session Management
  getSessions: () => request<Session[]>("/sessions", { method: "GET" }).catch(() => requestWithSessionQuery<Session[]>("/sessions").catch(() => [])), // Try both auth/public modes or just fetch public
  
  // Correction: getSessions should not require a session ID header if we are selecting one.
  // We need a helper that doesn't enforce session ID.
  getSessionsPublic: async () => {
    const res = await fetch(`${BASE_URL}/sessions`);
    if (!res.ok) throw new Error("Failed to list sessions");
    return res.json() as Promise<Session[]>;
  },

  deleteSession: (id: string) => fetch(`${BASE_URL}/sessions/${id}`, { method: "DELETE" }).then(r => r.json()),

  createSession: (title: string, workspaceId: string) => 
      fetch(`${BASE_URL}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, workspace_id: workspaceId, language: "python" })
      }).then(r => r.json() as Promise<Session>),

  // Threads
  getThreads: () => requestWithSessionQuery<Thread[]>(`/threads`),
  
  createThread: (title: string, type: "topic" | "breakout" = "topic", anchor?: { start: number, end: number }) => {
    const sessionId = getSessionId();
    if (!sessionId) throw new Error("No session");
    const payload: any = { 
        session_id: sessionId,
        title, 
        type
    };
    if (anchor) {
        payload.anchor = { line_start: anchor.start, line_end: anchor.end };
    }
    return request<Thread>(`/threads`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  createBreakout: (range: { start_line: number; end_line: number }, title?: string) =>
    request<Thread>(`/session/{session_id}/breakout`, {
      method: "POST",
      body: JSON.stringify({ range, title })
    }),

  getMessages: (threadId: string) => request<Message[]>(`/threads/${threadId}/messages`),

  postMessage: (threadId: string, content: string, role: "user" | "assistant" = "user") => 
    request<Message>(`/threads/${threadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ role, content })
    }),

  generateReply: (threadId: string, mode: "global" | "breakout", includeCode: boolean) =>
    request<Message>(`/threads/${threadId}/assistant_reply`, {
        method: "POST",
        body: JSON.stringify({ mode, include_code: includeCode })
    }),

  generateThreadSummary: (threadId: string) =>
    request<{ summary: string }>(`/threads/${threadId}/summary`, {
      method: "POST"
    }),

  // Code
  saveCodeSnapshot: (
    content: string,
    cursor?: { line: number; col: number },
    selectionRange?: { start_line: number; start_col: number; end_line: number; end_col: number },
    filePath?: string
  ) =>
    request<CodeSnapshot>(`/session/{session_id}/snapshot`, {
      method: "POST",
      body: JSON.stringify({ 
          content, 
          cursor_line: cursor?.line, 
          cursor_col: cursor?.col,
          selection_range: selectionRange,
          file_path: filePath
      })
    }),

  createCodeState: (content: string, traceId?: string) => {
    const sessionId = getSessionId();
    if (!sessionId) throw new Error("No session");
    return request<{ code_state_id: string; content_hash: string }>(`/code_states`, {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, content, trace_id: traceId })
    });
  },

  runCode: (code: string) =>
    request<{ ok: boolean; mode: string; exit_code: number | null; stdout: string; stderr: string; duration_ms: number; timed_out: boolean }>(
      `/session/{session_id}/run`,
      { method: "POST", body: JSON.stringify({ code }) }
    ),

  testCode: (code: string) =>
    request<{ ok: boolean; mode: string; exit_code: number | null; stdout: string; stderr: string; duration_ms: number; timed_out: boolean }>(
      `/session/{session_id}/test`,
      { method: "POST", body: JSON.stringify({ code }) }
    ),

  getLatestCode: async () => {
    const replay = await api.replaySession();
    return replay.latest_snapshot;
  },

  replaySession: () =>
    request<{
      session: Session;
      threads: Thread[];
      markers: any[];
      latest_snapshot: CodeSnapshot | null;
      messages: Message[];
    }>(`/session/{session_id}/replay`),

  getMarkers: (fileId?: string) =>
    requestWithSessionQuery<MarkerBrief[]>(
      fileId ? `/markers?file_id=${encodeURIComponent(fileId)}` : "/markers"
    ),

  // Workspace Persistence
  saveWorkspace: (files: Record<string, string>, entrypoint: string) =>
    request<{ ok: boolean }>(`/sessions/{session_id}/workspace`, {
      method: "POST",
      body: JSON.stringify({ files, entrypoint })
    }),

  getWorkspace: () =>
    request<{ files: Record<string, string>; entrypoint: string }>(`/sessions/{session_id}/workspace`, {
      method: "GET"
    }),

  // Events
  reportEvent: (eventType: string, payload: any, traceId?: string, codeStateId?: string) => 
    request<any>(`/session/{session_id}/event`, {
      method: "POST",
      body: JSON.stringify({ type: eventType, payload, trace_id: traceId, code_state_id: codeStateId })
    }),

  reportTelemetryBatch: (sessionId: string, events: any[]) =>
    request<{ ok: boolean; path: string; count: number }>(`/telemetry/batch`, {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, events })
    }),

  endSession: (reason?: string) =>
    request<{ ok: boolean; session_id: string; event_count: number; log_path: string }>(`/sessions/{session_id}/end`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  
  // =========================================================
  // ORACLE API
  // =========================================================

  oracleCreateTask: (projectId?: string) =>
    request<CreateTaskResponse>("/oracle/task", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId })
    }),

  oracleGetTask: (taskId: string) =>
    request<{ task_id: string; versions: any[] }>(`/oracle/task/${taskId}`, { method: "GET" }),

  oracleGenerateSpec: (taskId: string, body: SpecBody) =>
    request<GenerateSpecResponse>(`/oracle/task/${taskId}/version/spec`, {
      method: "POST",
      body: JSON.stringify(body)
    }),

  oracleConfirm: (versionId: string, body: ConfirmBody) =>
    request<ConfirmResponse>(`/oracle/version/${versionId}/confirm`, {
      method: "POST",
      body: JSON.stringify(body)
    }),

  oracleGenerateTests: (versionId: string, body: GenerateTestsBody) =>
    request<GenerateTestsResponse>(`/oracle/version/${versionId}/generate-tests`, {
      method: "POST",
      body: JSON.stringify(body)
    }),

  oracleRun: (versionId: string, body: RunBody) =>
    request<RunResponse>(`/oracle/version/${versionId}/run`, {
      method: "POST",
      body: JSON.stringify(body)
    }),

  oracleGetVersion: (versionId: string) =>
    request<any>(`/oracle/version/${versionId}`, { method: "GET" }),
};
