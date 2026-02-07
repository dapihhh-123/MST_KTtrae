import { useMemo, useReducer, useRef, useEffect, useState } from "react";
import GlobalChat from "./GlobalChat";
import EditorPane, { DEFAULT_CODE } from "./EditorPane";
import ConsolePane from "./ConsolePane";
import EducationPane from "./EducationPane";
import OracleFloatingPanel from "./oracle/OracleFloatingPanel"; // Import Oracle Panel
import FileExplorer from "./FileExplorer";
import WorkspaceTabs from "./WorkspaceTabs";

import type { AIPresenceState, Breakout, GlobalThread, Range, Message } from "../types";
import type { AgentAction, UIAction } from "../actions";
import { workspaceReducer, initialWorkspaceState, WorkspaceState, WorkspaceAction } from "../types/workspace";

import { uid, now } from "../utils";
import { playAgentActions, type EditorAPI } from "../actionPlayer";
import { api } from "../services/api";
import { socket } from "../services/socket";
import { makeChunkKey } from "../utils/stableKey";
import { resetSessionLocal } from "../services/session";

type AppState = {
  // code: string; // REPLACED by workspace
  workspace: WorkspaceState;
  chatCollapsed: boolean;
  explorerCollapsed: boolean; // New state for explorer

  ai: AIPresenceState;

  threads: GlobalThread[];
  breakouts: Breakout[];
  activeBreakoutId: string | null;

  consoleEntries: any[];
  highlights: { spans: any[]; expiresAt: number; traceId?: string } | null;
  editorOps: { ops: any[]; traceId?: string } | null;
  diagnosis: { data: any; traceId?: string } | null;
  intervention: { data: any; traceId?: string } | null;
  markers: any[];
};

type ExtendedUIAction = UIAction | { type: "WORKSPACE_ACTION"; action: WorkspaceAction } | { type: "SET_EXPLORER_COLLAPSED"; collapsed: boolean };

function reducer(state: AppState, action: ExtendedUIAction): AppState {
  switch (action.type) {
    case "SET_CHAT_COLLAPSED":
      return { ...state, chatCollapsed: action.collapsed };
    
    case "SET_EXPLORER_COLLAPSED":
      return { ...state, explorerCollapsed: action.collapsed };

    case "WORKSPACE_ACTION":
      return { ...state, workspace: workspaceReducer(state.workspace, action.action) };

    case "SET_CODE":
      // Legacy support: update the active file or main.py
      return {
        ...state,
        workspace: {
          ...state.workspace,
          files: {
            ...state.workspace.files,
            [state.workspace.activeFile]: action.code
          }
        }
      };

    case "SET_THREADS":
      return { ...state, threads: action.threads };

    case "AI_SET_PRESENCE":
      return { ...state, ai: { ...state.ai, ...action.presence } };

    case "THREAD_ADD":
      return { ...state, threads: [...state.threads, action.thread] };

    case "THREAD_TOGGLE":
      return {
        ...state,
        threads: state.threads.map((t) =>
          t.id === action.threadId && t.kind === "topic"
            ? { ...t, collapsed: !t.collapsed }
            : t
        )
      };

    case "THREAD_SET_SUMMARY":
      return {
        ...state,
        threads: state.threads.map((t) =>
          t.id === action.threadId && t.kind === "topic" ? { ...t, summary: action.summary } : t
        )
      };

    case "THREAD_APPEND_MESSAGE":
      return {
        ...state,
        threads: state.threads.map((t) =>
          t.id === action.threadId
            ? t.kind === "topic"
              ? { ...t, messages: [...(t.messages ?? []), action.message] }
              : t
            : t
        )
      };

    case "THREAD_UPDATE_MESSAGE":
      return {
        ...state,
        threads: state.threads.map((t) => {
          if (t.id !== action.threadId) return t;
          if (t.kind !== "topic") return t;
          const msgs = t.messages ?? [];
          return {
            ...t,
            messages: msgs.map((m: any) =>
              m.id === action.messageId ? { ...m, ...action.patch } : m
            )
          };
        })
      };

    case "BREAKOUT_ADD":
      return { ...state, breakouts: [...state.breakouts, action.breakout] };

    case "BREAKOUT_SET_OPEN":
      return {
        ...state,
        breakouts: state.breakouts.map((b) =>
          b.id === action.breakoutId ? { ...b, open: action.open } : b
        )
      };

    case "BREAKOUT_SET_POSITION":
      return {
        ...state,
        breakouts: state.breakouts.map((b) =>
          b.id === action.breakoutId ? { ...b, position: action.position } : b
        )
      };

    case "BREAKOUT_SET_SUMMARY":
      return {
        ...state,
        breakouts: state.breakouts.map((b) =>
          b.id === action.breakoutId ? { ...b, summary: action.summary } : b
        )
      };

    case "BREAKOUT_SET_ACTIVE":
      return { ...state, activeBreakoutId: action.breakoutId };

    case "BREAKOUT_APPEND_MESSAGE":
      return {
        ...state,
        breakouts: state.breakouts.map((b) =>
          b.id === action.breakoutId ? { ...b, messages: [...b.messages, action.message] } : b
        )
      };

    case "BREAKOUT_UPDATE_MESSAGE":
      return {
        ...state,
        breakouts: state.breakouts.map((b) => {
          if (b.id !== action.breakoutId) return b;
          return {
            ...b,
            messages: b.messages.map((m) => (m.id === action.messageId ? { ...m, ...action.patch } : m))
          };
        })
      };

    case "AI_STREAM_CHUNK": {
      // 1. Try Global Threads
      const tIndex = state.threads.findIndex(t => t.id === action.threadId);
      if (tIndex !== -1) {
        const t = state.threads[tIndex];
        if (t.kind !== "topic") return state;
        const msgs = t.messages || [];
        const mIndex = msgs.findIndex((m: any) => m.id === action.messageId);
        let newMsgs;
        if (mIndex !== -1) {
          // Update existing
          newMsgs = msgs.map((m: any, i: any) =>
            i === mIndex ? { ...m, content: m.content + action.chunk } : m
          );
        } else {
          // Insert new (B2: Upsert logic)
          newMsgs = [...msgs, { id: action.messageId, role: "assistant" as const, content: action.chunk, createdAt: Date.now() }];
        }
        const newThreads = [...state.threads];
        newThreads[tIndex] = { ...t, messages: newMsgs };
        return { ...state, threads: newThreads };
      }

      // 2. Try Breakouts
      const bIndex = state.breakouts.findIndex(b => b.id === action.threadId);
      if (bIndex !== -1) {
        const b = state.breakouts[bIndex];
        const msgs = b.messages || [];
        const mIndex = msgs.findIndex(m => m.id === action.messageId);
        let newMsgs: Message[];
        if (mIndex !== -1) {
          newMsgs = msgs.map((m, i) => i === mIndex ? { ...m, content: m.content + action.chunk } : m);
        } else {
          newMsgs = [...msgs, { id: action.messageId, role: "assistant" as const, content: action.chunk, createdAt: Date.now() }];
        }
        const newBreakouts = [...state.breakouts];
        newBreakouts[bIndex] = { ...b, messages: newMsgs };
        return { ...state, breakouts: newBreakouts };
      }

      return state;
    }

    case "CONSOLE_APPEND":
      return { ...state, consoleEntries: [...state.consoleEntries, ...action.entries] };

    case "CONSOLE_CLEAR":
      return { ...state, consoleEntries: [] };

    case "HIGHLIGHT_SET": {
      const ttl = action.ttlMs ?? 8000;
      return {
        ...state,
        highlights: { spans: action.spans || [], expiresAt: Date.now() + ttl, traceId: action.traceId }
      };
    }

    case "EDITOR_OPS_SET":
      return (action.ops && action.ops.length > 0)
        ? { ...state, editorOps: { ops: action.ops || [], traceId: action.traceId } }
        : { ...state, editorOps: null };

    case "DIAGNOSIS_SET":
      return { ...state, diagnosis: { data: action.diagnosis, traceId: action.traceId } };

    case "INTERVENTION_SET":
      return { ...state, intervention: { data: action.plan, traceId: action.traceId } };

    case "SET_MARKERS":
      return { ...state, markers: action.markers || [] };

    default:
      return state;
  }
}

function initialState(): AppState {
  const generalThreadId = uid("thread");
  return {
    workspace: initialWorkspaceState,
    chatCollapsed: false,
    explorerCollapsed: false,
    ai: { cursor: null, caret: null, selection: null, bubble: null, loading: false },
    threads: [
      {
        id: generalThreadId,
        kind: "topic",
        title: "General",
        summary: "Global discussion (topic-thread). Local questions should be anchored as Breakouts.",
        messages: [{ id: uid("msg"), role: "assistant", content: "Hi! You can chat globally or create Breakouts anchored to code lines.", createdAt: now() }],
        collapsed: false,
        createdAt: now()
      }
    ],
    breakouts: [],
    activeBreakoutId: null,
    consoleEntries: [],
    highlights: null,
    editorOps: null,
    diagnosis: null,
    intervention: null,
    markers: []
  };
}

export default function IDE(props: { sessionId: string; onExit: () => void }) {
  const [state, dispatch] = useReducer(reducer, undefined as any, initialState);
  const [oracleOpen, setOracleOpen] = useState(false); // Toggle state for Oracle Panel
  
  // Task 2: Fix duplicated chunks using seen set
  // Key format: threadId:messageId:seq
  const seenChunksRef = useRef<Set<string>>(new Set());
  const bootedRef = useRef(false);
  const topicThreadIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    async function boot() {
      try {
        // Use the passed sessionId instead of initSession logic
        const sid = props.sessionId;
        console.log("IDE booting with session_id=" + sid);
        
        // Ensure localStorage is sync (optional, but good for other services reading it)
        localStorage.setItem("kt_session_id", sid);
        
        socket.connect();
        
        // Load Workspace State (Persistence)
        const wsState = await api.getWorkspace().catch(() => null);
        if (wsState && wsState.files) {
            dispatch({ type: "WORKSPACE_ACTION", action: { type: "INIT_WORKSPACE", payload: wsState } });
        } else {
            const replay = await api.replaySession().catch(() => null);
            if (replay?.latest_snapshot?.content) {
              // Initialize workspace with replay content
              // Assume replay is for "main.py" or whatever activeFile is
              dispatch({ type: "SET_CODE", code: replay.latest_snapshot.content });
            }
            // Re-fetch threads for replay context below
        }

        const replay = await api.replaySession().catch(() => null);
        
        const msgsByThread: Record<string, any[]> = {};
        (replay?.messages ?? []).forEach((m: any) => {
          const tid = m.thread_id ?? m.threadId;
          if (!tid) return;
          msgsByThread[tid] ||= [];
          msgsByThread[tid].push({ ...m, createdAt: m.created_at || m.createdAt || now() });
        });

        const backendThreads = replay?.threads ?? [];
        const globalThreads: GlobalThread[] = backendThreads
          .filter((t: any) => t.type === "global")
          .map((t: any) => ({
            id: t.id,
            kind: "topic",
            title: t.title || "General",
            summary: t.summary,
            messages: msgsByThread[t.id] || [],
            collapsed: false,
            createdAt: t.created_at || t.createdAt || now()
          }));

        const breakouts: Breakout[] = backendThreads
          .filter((t: any) => t.type === "breakout")
          .map((t: any) => ({
            id: t.id,
            title: t.title || "Breakout",
            anchorStartLine: t.anchor?.line_start || 0,
            anchorEndLine: t.anchor?.line_end || 0,
            open: false,
            messages: msgsByThread[t.id] || [],
            summary: t.summary || undefined
          }));

        if (globalThreads.length === 0) {
          globalThreads.push({
            id: replay?.session?.id || uid("thread"),
            kind: "topic",
            title: "General",
            summary: "Global discussion",
            messages: [],
            collapsed: false,
            createdAt: now()
          });
        }

        topicThreadIdRef.current = globalThreads.find((t) => t.kind === "topic")?.id ?? null;
        dispatch({ type: "SET_THREADS", threads: globalThreads });
        breakouts.forEach((b) => dispatch({ type: "BREAKOUT_ADD", breakout: b }));

        const markers = await api.getMarkers().catch(() => []);
        dispatch({ type: "SET_MARKERS", markers });
        const existing = new Set(breakouts.map((b) => b.id));
        (markers as any[]).forEach((mk: any) => {
          const bid = mk.thread_id || mk.threadId;
          if (!bid || existing.has(bid)) return;
          existing.add(bid);
          dispatch({
            type: "BREAKOUT_ADD",
            breakout: {
              id: bid,
              title: mk.title || "Marker",
              anchorStartLine: mk.line || 1,
              anchorEndLine: mk.line || 1,
              open: false,
              messages: []
            }
          });
        });

      } catch (e) {
        console.error("Boot error", e);
      }
    }
    boot();
    
    const unsub = socket.subscribe((data) => {
        const currentSid = api.getSessionId();
        if (data.session_id && currentSid && data.session_id !== currentSid) return;

        if (data.type === "ai_state") {
          const state = data.state;
          dispatch({
            type: "AI_SET_PRESENCE",
            presence: {
              status: state,
              loading: state === "thinking" || state === "writing",
              bubble:
                state === "thinking"
                  ? { emoji: "🤔", text: "Thinking..." }
                  : state === "writing"
                    ? { emoji: "✏️", text: "Writing..." }
                    : null
            }
          });
          return;
        }

        if (data.type === "assistant_message_begin") {
          const threadId = (data.thread_id && data.thread_id !== "global") ? data.thread_id : (topicThreadIdRef.current || data.thread_id);
          if (threadId && data.message_id) {
            dispatch({
              type: "AI_STREAM_CHUNK",
              threadId,
              messageId: data.message_id,
              chunk: ""
            });
          }
          return;
        }

        if (data.type === "ai_text_chunk") {
          const threadId = (data.thread_id && data.thread_id !== "global") ? data.thread_id : (topicThreadIdRef.current || data.thread_id);
          const chunkKey = makeChunkKey("global", threadId, data.message_id, data.seq ?? -1);
          if (data.seq !== undefined && seenChunksRef.current.has(chunkKey)) return;
          if (data.seq !== undefined) seenChunksRef.current.add(chunkKey);

          dispatch({
            type: "AI_STREAM_CHUNK",
            threadId,
            messageId: data.message_id,
            chunk: data.chunk || data.delta
          });
          return;
        }

        if (data.type === "ui.bubble_show") {
          const text = data.payload?.text || "";
          const ttlMs = data.payload?.ttl_ms || 8000;
          if (text) {
            dispatch({ type: "AI_SET_PRESENCE", presence: { bubble: { emoji: "💡", text } } });
            window.setTimeout(() => {
              dispatch({ type: "AI_SET_PRESENCE", presence: { bubble: null } });
            }, ttlMs);
          }
          return;
        }

        if (data.type === "highlight_spans") {
          const spans = data.spans || data.data?.spans || data.payload?.spans || [];
          const ttlMs = data.ttl_ms || data.ttlMs || data.data?.ttl_ms || data.data?.ttlMs;
          dispatch({ type: "HIGHLIGHT_SET", spans, ttlMs, traceId: data.trace_id || data.data?.trace_id });
          if (Array.isArray(spans) && spans.length > 0) {
            const s = spans[0];
            const lineStart = s.line_start ?? s.lineStart ?? s.start_line ?? s.startLine ?? 1;
            const lineEnd = s.line_end ?? s.lineEnd ?? s.end_line ?? s.endLine ?? lineStart;
            dispatch({
              type: "AI_SET_PRESENCE",
              presence: {
                cursor: { line: lineStart, col: 1 },
                caret: { line: lineStart, col: 1 },
                bubble: { emoji: "👀", text: `Reviewing lines ${lineStart}-${lineEnd}` }
              }
            });
          }
          return;
        }

        if (data.type === "editor_ops") {
          const ops = data.ops || data.data?.ops || data.payload?.ops || [];
          dispatch({ type: "EDITOR_OPS_SET", ops, traceId: data.trace_id || data.data?.trace_id });
          return;
        }

        if (data.type === "diagnosis_ready") {
          const d = data.data || data.payload || {};
          const tid = data.trace_id || data.data?.trace_id;
          dispatch({ type: "DIAGNOSIS_SET", diagnosis: d, traceId: tid });
          const spans = d.spans || d.data?.spans;
          if (spans && Array.isArray(spans) && spans.length > 0) {
            dispatch({ type: "HIGHLIGHT_SET", spans, ttlMs: 10000, traceId: tid });
            const s = spans[0];
            const lineStart = s.line_start ?? s.lineStart ?? s.start_line ?? s.startLine ?? 1;
            const lineEnd = s.line_end ?? s.lineEnd ?? s.end_line ?? s.endLine ?? lineStart;
            dispatch({
              type: "AI_SET_PRESENCE",
              presence: {
                cursor: { line: lineStart, col: 1 },
                caret: { line: lineStart, col: 1 },
                bubble: { emoji: "🧭", text: `Diagnosis: ${d.label || "check"} @ ${lineStart}-${lineEnd}` }
              }
            });
          }
          return;
        }

        if (data.type === "intervention_plan") {
          dispatch({ type: "INTERVENTION_SET", plan: data.data || data.payload || {}, traceId: data.trace_id || data.data?.trace_id });
          return;
        }
    });

    return () => {
        unsub();
        socket.disconnect();
    };
  }, [props.sessionId]); // Re-boot if sessionId changes

  // Snapshot Throttling (2.7-C) & Workspace Persistence
  const activeCode = state.workspace.files[state.workspace.activeFile] || "";
  useEffect(() => {
    const timer = setTimeout(() => {
       // 1. Legacy Snapshot (Active File)
       if (activeCode && activeCode !== DEFAULT_CODE) {
          const cursor = editorApiRef.current?.getCursor() || undefined;
          const sel = editorApiRef.current?.getSelectionRange() || undefined;
          api.saveCodeSnapshot(activeCode, cursor, sel, state.workspace.activeFile).catch(e => console.error("Snapshot failed", e));
       }
       // 2. Full Workspace Persistence
       api.saveWorkspace(state.workspace.files, state.workspace.entrypoint).catch(e => console.error("Workspace save failed", e));
    }, 2000); // 2s debounce
    return () => clearTimeout(timer);
  }, [activeCode, state.workspace.activeFile, state.workspace.files, state.workspace.entrypoint]);

  const editorApiRef = useRef<EditorAPI | null>(null);

  // 用于取消上一轮 agent action（避免抢话/并发冲突）
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const opsPayload = state.editorOps;
    if (!opsPayload || !opsPayload.ops || opsPayload.ops.length === 0) return;
    const editor = editorApiRef.current;
    if (!editor) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const { signal } = abortRef.current;

    const toRange = (r: any): Range => ({
      startLine: r.start_line ?? r.startLine ?? r.start_line_number ?? r.startLineNumber ?? 1,
      startCol: r.start_col ?? r.startCol ?? 1,
      endLine: r.end_line ?? r.endLine ?? r.end_line_number ?? r.endLineNumber ?? (r.start_line ?? r.startLine ?? 1),
      endCol: r.end_col ?? r.endCol ?? 1
    });

    (async () => {
      dispatch({ type: "AI_SET_PRESENCE", presence: { loading: true, status: "writing" } });
      for (const op of opsPayload.ops) {
        if (signal.aborted) return;
        const range = toRange(op.range || {});
        const pos = { line: range.startLine, col: range.startCol };
        dispatch({ type: "AI_SET_PRESENCE", presence: { cursor: pos, caret: pos } });

        const kind = op.op || op.type;
        if (kind === "replace") {
          await editor.replaceRange(range, op.text ?? "", !!op.typing, op.speed_ms || 10);
        } else if (kind === "insert") {
          await editor.insertAt(range, op.text ?? "", !!op.typing, op.speed_ms || 10);
        } else if (kind === "delete") {
          editor.deleteRange(range);
        } else if (kind === "reveal_line") {
          editor.revealLine(range.startLine);
        } else if (kind === "set_selection") {
          editor.setSelection(range);
        }
      }
      dispatch({ type: "AI_SET_PRESENCE", presence: { loading: false, status: "done", bubble: null } });
      dispatch({ type: "EDITOR_OPS_SET", ops: [] });
    })();
  }, [state.editorOps]);

  const breakoutOpen = useMemo(() => state.breakouts.some((b) => b.open), [state.breakouts]);
  const chatBlurred = breakoutOpen && state.activeBreakoutId !== null;

  function onSendGlobal(threadId: string, msg: any) {
    // 用户发消息：先写入 UI (Optimistic)
    dispatch({ type: "THREAD_APPEND_MESSAGE", threadId, message: msg });

    // 用户主动输入时：取消 pending agent
    abortRef.current?.abort();

    // runAgent({ type: "GLOBAL_MESSAGE", threadId, text: msg.content, code: state.code });
    api.postMessage(threadId, msg.content, "user").then((serverMsg) => {
        // Task 3: Update message with server ID but keep client_id
        if (serverMsg) {
             dispatch({
                 type: "THREAD_UPDATE_MESSAGE",
                 threadId,
                 messageId: msg.id, // temp ID
                 patch: serverMsg   // Merges server ID, preserves client_id if not in patch
             });
        }
        return api.generateReply(threadId, "global", true);
    }).catch(e => console.error("Send failed", e));
  }

  function onSendBreakout(breakoutId: string, msg: any) {
    dispatch({ type: "BREAKOUT_APPEND_MESSAGE", breakoutId, message: msg });
    abortRef.current?.abort();
    // runAgent({ type: "BREAKOUT_MESSAGE", breakoutId, text: msg.content, code: state.code });
    api.postMessage(breakoutId, msg.content, "user").then(() => {
         return api.generateReply(breakoutId, "breakout", true);
    }).catch(e => console.error("Send failed", e));
  }

  function createBreakout(startLine: number, endLine: number) {
    // const id = uid("breakout");
    api.createBreakout({ start_line: startLine, end_line: endLine }, "Breakout").then(thread => {
        const id = thread.id;
        dispatch({
          type: "BREAKOUT_ADD",
          breakout: {
            id,
            title: "Breakout",
            anchorStartLine: startLine,
            anchorEndLine: endLine,
            open: true,
            messages: [{ id: uid("bmsg"), role: "assistant", content: "Breakout created. Ask questions in situ.", createdAt: now() }]
          }
        });
        dispatch({ type: "BREAKOUT_SET_ACTIVE", breakoutId: id });

        // 在 global chat 里加一个 summary 卡（provenance）
        dispatch({
          type: "THREAD_ADD",
          thread: {
            id: uid("summary"),
            kind: "breakoutSummary",
            title: "Breakout summary",
            summary: `A local thread has been created for lines ${startLine}-${endLine}.`,
            sourceMessageIds: [],
            breakoutId: id,
            createdAt: now()
          }
        });
    }).catch(e => console.error("Create breakout failed", e));
  }

  function openBreakout(id: string) {
    dispatch({ type: "BREAKOUT_SET_OPEN", breakoutId: id, open: true });
    dispatch({ type: "BREAKOUT_SET_ACTIVE", breakoutId: id });
  }

  function closeBreakout(id: string) {
    dispatch({ type: "BREAKOUT_SET_OPEN", breakoutId: id, open: false });
    api.generateThreadSummary(id).then((r) => {
      dispatch({ type: "BREAKOUT_SET_SUMMARY", breakoutId: id, summary: r.summary });
    }).catch(() => {});
    if (state.activeBreakoutId === id) {
      dispatch({ type: "BREAKOUT_SET_ACTIVE", breakoutId: null });
    }
  }

  function focusBreakout(id: string) {
    dispatch({ type: "BREAKOUT_SET_ACTIVE", breakoutId: id });
  }

  // Demo: AI 像论文一样写代码（通过 actions replay）
  function demoAIWriteCode(explicitRange?: Range) {
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    // Task B/C: Dynamic insertion target
    const target = editorApiRef.current?.getInsertionTarget(explicitRange);
    if (!target) return;

    // insertAt uses start of range, so align cursor there
    const insertPos = { line: target.range.startLine, col: target.range.startCol };
    
    // If we have a selection, we likely want to replace it.
    // If it's a cursor/explicit point, replaceRange with empty range acts as insert.
    const actionType = target.kind === "selection" ? "EDITOR_REPLACE" : "EDITOR_INSERT";

    const actions: AgentAction[] = [
      { type: "AI_SET_PRESENCE", presence: { loading: true, bubble: { emoji: "✍️", text: "Writing code..." }, cursor: insertPos, caret: insertPos } },
      { type: "EDITOR_REVEAL_LINE", line: insertPos.line },
      { 
        type: actionType, 
        range: target.range, 
        text: "return (event1['start'] < event2['end']) and (event2['start'] < event1['end'])\n", 
        typing: true, 
        speedMs: 10, 
        provenance: true 
      },
      { type: "WAIT", ms: 400 },
      { type: "AI_SET_PRESENCE", presence: { loading: false, bubble: { emoji: "🤔", text: "Thinking..." } } },
      { type: "WAIT", ms: 800 },
      { type: "AI_SET_PRESENCE", presence: { bubble: null } }
    ];

    playAgentActions({ actions, dispatch, editor: editorApiRef.current, signal: abortRef.current.signal });
  }

  async function runProgram() {
    abortRef.current?.abort();
    dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("log"), kind: "info", text: "RUN..." }] });

    const traceId = uid("trace");
    let codeStateId: string | undefined;
    try {
      const cs = await api.createCodeState(activeCode, traceId);
      codeStateId = cs.code_state_id;
    } catch {}

    const cursor = editorApiRef.current?.getCursor() || undefined;
    const sel = editorApiRef.current?.getSelectionRange() || undefined;
    await api.saveCodeSnapshot(activeCode, cursor, sel, state.workspace.activeFile).catch(() => {});

    api.reportEvent("run", { run_id: uid("run"), run_command: "python", cwd: ".", code_len: activeCode.length }, traceId, codeStateId).catch(() => {});
    try {
      // Legacy RUN button: uses active code
      const res = await api.runCode(activeCode);
      if (res.stdout) dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("out"), kind: "log", text: res.stdout.trimEnd() }] });
      if (res.stderr) dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("err"), kind: "error", text: res.stderr.trimEnd() }] });
      if (res.timed_out) dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("to"), kind: "error", text: "Timed out" }] });
      api.reportEvent(res.ok ? "run_ok" : "run_fail", {
        success: res.ok,
        exit_code: res.exit_code,
        stdout_snippet: res.stdout,
        stderr_snippet: res.stderr,
        duration_ms: res.duration_ms,
        timed_out: res.timed_out
      }, traceId, codeStateId).catch(() => {});
    } catch (e) {
      dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("err"), kind: "error", text: String(e) }] });
      api.reportEvent("run_fail", { success: false, error: String(e) }, traceId, codeStateId).catch(() => {});
    }
  }

  async function runTests() {
    abortRef.current?.abort();
    dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("log"), kind: "info", text: "TEST..." }] });

    const traceId = uid("trace");
    let codeStateId: string | undefined;
    try {
      const cs = await api.createCodeState(activeCode, traceId);
      codeStateId = cs.code_state_id;
    } catch {}

    const cursor = editorApiRef.current?.getCursor() || undefined;
    const sel = editorApiRef.current?.getSelectionRange() || undefined;
    await api.saveCodeSnapshot(activeCode, cursor, sel, state.workspace.activeFile).catch(() => {});

    api.reportEvent("test", { test_id: uid("test"), run_command: "python -m pytest", cwd: ".", code_len: activeCode.length }, traceId, codeStateId).catch(() => {});
    try {
      const res = await api.testCode(activeCode);
      if (res.stdout) dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("out"), kind: "log", text: res.stdout.trimEnd() }] });
      if (res.stderr) dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("err"), kind: "error", text: res.stderr.trimEnd() }] });
      if (res.timed_out) dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("to"), kind: "error", text: "Timed out" }] });
      api.reportEvent(res.ok ? "test_pass" : "test_fail", {
        success: res.ok,
        exit_code: res.exit_code,
        stdout_snippet: res.stdout,
        stderr_snippet: res.stderr,
        duration_ms: res.duration_ms,
        timed_out: res.timed_out
      }, traceId, codeStateId).catch(() => {});
    } catch (e) {
      dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("err"), kind: "error", text: String(e) }] });
      api.reportEvent("test_fail", { success: false, error: String(e) }, traceId, codeStateId).catch(() => {});
    }
  }

  async function saveNow() {
    const cursor = editorApiRef.current?.getCursor() || undefined;
    const sel = editorApiRef.current?.getSelectionRange() || undefined;
    await api.saveCodeSnapshot(activeCode, cursor, sel, state.workspace.activeFile).catch(() => {});
    api.reportEvent("edit", { event_subtype: "save", file_path: state.workspace.activeFile, cursor_line: cursor?.line, cursor_col: cursor?.col }).catch(() => {});
    dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("save"), kind: "info", text: "SAVED (snapshot + event)" }] });
  }

  async function endNow() {
    try {
      const res = await api.endSession("manual_end");
      dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("end"), kind: "info", text: `SESSION_ENDED: ${res.session_id} events=${res.event_count}` }] });
    } catch (e) {
      dispatch({ type: "CONSOLE_APPEND", entries: [{ id: uid("enderr"), kind: "error", text: `END failed: ${String(e)}` }] });
    }
  }

  const getWorkspaceSnapshot = () => ({
      files: state.workspace.files,
      entrypoint: state.workspace.entrypoint
  });

  return (
    <div className="appRoot">
      <div className="topBar">
        <div className="left">
          <div className="brand">
            <span>Codellaborator</span>
            <span className="pill">UI clone+</span>
          </div>

          <button className="btn ghost" onClick={() => dispatch({ type: "SET_CHAT_COLLAPSED", collapsed: !state.chatCollapsed })}>
            {state.chatCollapsed ? "Show Chat" : "Hide Chat"}
          </button>
          
          <button className="btn ghost" onClick={() => dispatch({ type: "SET_EXPLORER_COLLAPSED", collapsed: !state.explorerCollapsed })}>
            {state.explorerCollapsed ? "Show Files" : "Hide Files"}
          </button>

          <button className="btn" onClick={() => demoAIWriteCode()}>Demo: AI write</button>
          <button className="btn" onClick={() => demoAIWriteCode({ startLine: 15, startCol: 1, endLine: 15, endCol: 1 })}>Test Explicit (L15)</button>
          <button className="btn" onClick={() => api.reportEvent("compile_error", { message: "Simulated Error", problem_id: "999" })}>Simulate Error</button>
          <button className="btn" onClick={() => editorApiRef.current?.createBreakoutFromSelection()}>+ Breakout</button>
        </div>

        <div className="right">
          <button className={`btn ${oracleOpen ? "active" : "ghost"}`} onClick={() => setOracleOpen(!oracleOpen)}>🔮 Oracle</button>
          <button className="btn ghost" onClick={saveNow}>SAVE</button>
          <button className="btn ghost" onClick={endNow}>END</button>
          <button
            className="btn ghost"
            onClick={props.onExit}
          >
            Exit Session
          </button>
          <button className="btn" onClick={() => dispatch({ type: "CONSOLE_CLEAR" })}>Clear Console</button>
          <button className="btn" onClick={runTests}>TEST</button>
          <button className="btn primary" onClick={runProgram}>RUN</button>
        </div>
      </div>

      <div className="bodyRow">
        <GlobalChat
          collapsed={state.chatCollapsed}
          blurred={chatBlurred}
          threads={state.threads}
          onToggleCollapsePanel={() => dispatch({ type: "SET_CHAT_COLLAPSED", collapsed: !state.chatCollapsed })}
          onSend={onSendGlobal}
          onToggleThread={(id) => dispatch({ type: "THREAD_TOGGLE", threadId: id })}
          onNavigateToBreakout={(bid) => openBreakout(bid)}
          onSummarizeThread={(threadId) => {
            api.generateThreadSummary(threadId).then((r) => {
              dispatch({ type: "THREAD_SET_SUMMARY", threadId, summary: r.summary });
            }).catch((e) => console.error("summary failed", e));
          }}
        />

        <div className="editorAndConsole">
          <div style={{ display: "flex", flex: 1, overflow: "hidden", minHeight: 0 }}>
             {!state.explorerCollapsed && (
                 <FileExplorer 
                    workspace={state.workspace}
                    dispatch={(action) => dispatch({ type: "WORKSPACE_ACTION", action })}
                 />
             )}
             
             <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                <WorkspaceTabs 
                    workspace={state.workspace}
                    dispatch={(action) => dispatch({ type: "WORKSPACE_ACTION", action })}
                />
                <EditorPane
                  ref={(api) => { editorApiRef.current = api; }}
                  code={activeCode}
                  onCodeChange={(c) => state.workspace.activeFile && dispatch({ type: "WORKSPACE_ACTION", action: { type: "FILE_UPDATE", payload: { path: state.workspace.activeFile, content: c } } })}
                  breakouts={state.breakouts}
                  activeBreakoutId={state.activeBreakoutId}
                  onOpenBreakout={openBreakout}
                  onCloseBreakout={closeBreakout}
                  onFocusBreakout={focusBreakout}
                  onSendBreakout={onSendBreakout}
                  ai={state.ai}
                  highlights={state.highlights}
                  onTelemetryEvent={(type, payload) => api.reportEvent(type, payload).catch(() => {})}
                  onCreateBreakoutFromSelection={(s, e) => createBreakout(s, e)}
                  onUpdateBreakoutPosition={(id, x, y) => dispatch({ type: "BREAKOUT_SET_POSITION", breakoutId: id, position: { x, y } })}
                />
             </div>
          </div>

          <EducationPane
            diagnosis={state.diagnosis}
            intervention={state.intervention}
            onSubmitUnlock={(p) => api.reportEvent("unlock_attempt", p).catch((e) => console.error("unlock_attempt failed", e))}
            onSubmitRecap={(p) => api.reportEvent("recap_response", p).catch((e) => console.error("recap_response failed", e))}
          />

          <ConsolePane
            entries={state.consoleEntries}
            onClear={() => dispatch({ type: "CONSOLE_CLEAR" })}
          />
        </div>
      </div>
      
      {oracleOpen && (
          <OracleFloatingPanel 
              onClose={() => setOracleOpen(false)} 
              getSnapshot={getWorkspaceSnapshot}
          />
      )}
    </div>
  );
}
