import type { AgentAction, UIAction } from "./actions";
import type { Range } from "./types";
import { sleep } from "./utils";

export type InsertionTarget = {
  range: Range;
  kind: "selection" | "cursor" | "fallback" | "explicit";
  position: { line: number; col: number };
};

export interface EditorAPI {
  revealLine(line: number): void;
  setSelection(range: Range): void;
  deleteRange(range: Range): void;
  replaceRange(range: Range, text: string, typing: boolean, speedMs: number): Promise<void>;
  insertAt(range: Range, text: string, typing: boolean, speedMs: number): Promise<void>;
  highlightProvenance(range: Range, ttlMs: number): void;
  createBreakoutFromSelection(): void;
  getInsertionTarget(preferred?: Range): InsertionTarget;
  getCursor(): { line: number; col: number } | null;
  getSelectionRange(): { start_line: number; start_col: number; end_line: number; end_col: number } | null;
}

export async function playAgentActions(params: {
  actions: AgentAction[];
  dispatch: React.Dispatch<UIAction>;
  editor: EditorAPI | null;
  signal: AbortSignal;
}) {
  const { actions, dispatch, editor, signal } = params;

  for (const action of actions) {
    if (signal.aborted) return;

    switch (action.type) {
      case "WAIT":
        await sleep(action.ms);
        break;

      case "AI_SET_PRESENCE":
        dispatch({ type: "AI_SET_PRESENCE", presence: action.presence });
        break;

      case "EDITOR_REVEAL_LINE":
        editor?.revealLine(action.line);
        break;

      case "EDITOR_SET_SELECTION":
        editor?.setSelection(action.range);
        break;

      case "EDITOR_DELETE":
        editor?.deleteRange(action.range);
        break;

      case "EDITOR_INSERT":
        await editor?.insertAt(action.range, action.text, !!action.typing, action.speedMs || 20);
        if (action.provenance) {
          // calculate end position for highlighting? 
          // simplifying: highlight the inserted range logic needs to be robust, 
          // here we just blindly highlight same start line for demo
          editor?.highlightProvenance(action.range, 5000); 
        }
        break;

      case "EDITOR_REPLACE":
        await editor?.replaceRange(action.range, action.text, !!action.typing, action.speedMs || 20);
        if (action.provenance) {
          editor?.highlightProvenance(action.range, 5000);
        }
        break;

      case "THREAD_APPEND_MESSAGE":
        dispatch({ type: "THREAD_APPEND_MESSAGE", threadId: action.threadId, message: action.message });
        break;

      case "BREAKOUT_APPEND_MESSAGE":
        dispatch({ type: "BREAKOUT_APPEND_MESSAGE", breakoutId: action.breakoutId, message: action.message });
        break;

      case "BREAKOUT_SET_OPEN":
        dispatch({ type: "BREAKOUT_SET_OPEN", breakoutId: action.breakoutId, open: action.open });
        break;

      case "CONSOLE_APPEND":
        dispatch({ type: "CONSOLE_APPEND", entries: action.entries });
        break;

      case "CONSOLE_CLEAR":
        dispatch({ type: "CONSOLE_CLEAR" });
        break;
    }
  }
}
