import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import Editor, { OnMount } from "@monaco-editor/react";
import type * as monaco from "monaco-editor";
import type { AIPresenceState, Breakout, Range } from "../types";
import BreakoutOverlay from "./BreakoutOverlay";
import { AIPresenceWidget, BreakoutSummaryWidget } from "../monacoWidgets";
import { sleep } from "../utils";
import type { EditorAPI, InsertionTarget } from "../actionPlayer";

type MonacoEditor = monaco.editor.IStandaloneCodeEditor;

export const DEFAULT_CODE = `# TODO: Create a new event and check for conflicts
def times_overlap(event1, event2):
    pass

# Unit tests
def test_times_overlap():
    pass
`;

export default forwardRef<EditorAPI, {
  code: string;
  onCodeChange: (code: string) => void;

  breakouts: Breakout[];
  activeBreakoutId: string | null;
  onOpenBreakout: (id: string) => void;
  onCloseBreakout: (id: string) => void;
  onFocusBreakout: (id: string) => void;
  onSendBreakout: (breakoutId: string, msg: any) => void;

  ai: AIPresenceState;
  highlights: { spans: any[]; expiresAt: number; traceId?: string } | null;
  onTelemetryEvent: (type: string, payload: any) => void;
  onCreateBreakoutFromSelection: (startLine: number, endLine: number) => void;
  onUpdateBreakoutPosition: (id: string, x: number, y: number) => void;
}>(function EditorPane(props, ref) {
  const editorRef = useRef<MonacoEditor | null>(null);
  const monacoRef = useRef<typeof monaco | null>(null);
  const latestProps = useRef(props);
  latestProps.current = props;

  // overlay position refresh
  const [overlayTick, setOverlayTick] = useState(0);

  // decorations
  const breakoutDecoRef = useRef<string[]>([]);
  const glyphDecoRef = useRef<string[]>([]);
  const provDecoRef = useRef<string[]>([]);
  const diagDecoRef = useRef<string[]>([]);

  // AI widgets
  const aiCursorW = useRef<AIPresenceWidget | null>(null);
  const aiCaretW = useRef<AIPresenceWidget | null>(null);
  const aiBubbleW = useRef<AIPresenceWidget | null>(null);
  const summaryWidgetsRef = useRef<Map<string, BreakoutSummaryWidget>>(new Map());
  const lastActivityRef = useRef<number>(Date.now());
  const lastIdleSentRef = useRef<number>(0);
  const selectionTimerRef = useRef<number | null>(null);

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor as MonacoEditor;
    monacoRef.current = monaco as typeof monaco;

    editor.updateOptions({
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      smoothScrolling: true,
      fontSize: 13,
      glyphMargin: true // ✅ breakout anchor marker 需要
    });

    // AI widgets
    aiCursorW.current = new AIPresenceWidget("ai.cursor", "cursor");
    aiCaretW.current = new AIPresenceWidget("ai.caret", "caret");
    aiBubbleW.current = new AIPresenceWidget("ai.bubble", "bubble");

    editor.addContentWidget(aiCursorW.current);
    editor.addContentWidget(aiCaretW.current);
    editor.addContentWidget(aiBubbleW.current);

    editor.onDidScrollChange(() => setOverlayTick((x) => x + 1));
    editor.onDidLayoutChange(() => setOverlayTick((x) => x + 1));

    const markActivity = () => {
      lastActivityRef.current = Date.now();
    };

    editor.onDidChangeModelContent((e) => {
      markActivity();
      const changes = e.changes || [];
      if (changes.length === 0) return;

      const totalInsertedChars = changes.reduce((acc, c) => acc + (c.text || "").length, 0);
      const totalInsertedLines = changes.reduce((acc, c) => acc + ((c.text || "").split("\n").length - 1), 0);

      const first = changes[0];
      const changed_range = {
        startLine: first.range.startLineNumber,
        startCol: first.range.startColumn,
        endLine: first.range.endLineNumber,
        endCol: first.range.endColumn
      };

      const lines_deleted = changes.reduce((acc, c) => acc + Math.max(0, c.range.endLineNumber - c.range.startLineNumber), 0);
      const lines_added = totalInsertedLines;

      let event_subtype: "edit" | "paste" | "undo" | "redo" = "edit";
      if ((e as any).isUndoing) event_subtype = "undo";
      else if ((e as any).isRedoing) event_subtype = "redo";
      else if (totalInsertedChars > 50 || totalInsertedLines > 3) event_subtype = "paste";

      props.onTelemetryEvent("edit", {
        event_subtype,
        changed_range,
        lines_added,
        lines_deleted,
        chars_added: totalInsertedChars,
        change_count: changes.length
      });
    });

    editor.onDidChangeCursorSelection((e) => {
      markActivity();
      const sel = e.selection;
      const hasSelection = !!sel && !sel.isEmpty();
      if (selectionTimerRef.current) {
        window.clearTimeout(selectionTimerRef.current);
        selectionTimerRef.current = null;
      }
      if (!hasSelection) return;
      const range = {
        start_line: sel.startLineNumber,
        start_col: sel.startColumn,
        end_line: sel.endLineNumber,
        end_col: sel.endColumn
      };
      selectionTimerRef.current = window.setTimeout(() => {
        const ed = editorRef.current;
        if (!ed) return;
        const cur = ed.getSelection();
        if (!cur || cur.isEmpty()) return;
        if (
          cur.startLineNumber === sel.startLineNumber &&
          cur.endLineNumber === sel.endLineNumber &&
          cur.startColumn === sel.startColumn &&
          cur.endColumn === sel.endColumn
        ) {
          props.onTelemetryEvent("selection_dwell", { range, dwell_ms: 15000 });
        }
      }, 15000);
    });

    // ✅ 点击 glyph margin 打开 breakout
    editor.onMouseDown((e) => {
      const m = monacoRef.current;
      if (!m) return;
      const pos = e.target.position;
      if (!pos) return;

      const t = e.target.type;
      
      // LOGGING as requested by task A0
      // console.log("marker clicked debug", { type: t, pos, target: e.target });

      if (
        t === m.editor.MouseTargetType.GUTTER_GLYPH_MARGIN ||
        t === m.editor.MouseTargetType.GUTTER_LINE_NUMBERS
      ) {
        console.log("Clicked gutter/glyph at line", pos.lineNumber);
        const line = pos.lineNumber;
        const p = latestProps.current;
        const b = p.breakouts.find((x) => line >= x.anchorStartLine && line <= x.anchorEndLine);
        if (b) {
          console.log("Found breakout:", b.id);
          p.onOpenBreakout(b.id);
          editor.revealLineInCenter(b.anchorStartLine);
        } else {
          console.log("No breakout found for line", line);
        }
      }
    });
  };

  useEffect(() => {
    const ed = editorRef.current;
    const m = monacoRef.current;
    if (!ed || !m) return;

    const nextIds = new Set<string>();
    for (const b of props.breakouts) {
      if (!b.summary) continue;
      const id = `breakout.summary.${b.id}`;
      nextIds.add(id);
      let w = summaryWidgetsRef.current.get(id);
      if (!w) {
        w = new BreakoutSummaryWidget(id, () => props.onOpenBreakout(b.id));
        summaryWidgetsRef.current.set(id, w);
        ed.addContentWidget(w);
      }
      w.setContent(`Breakout summary #${b.anchorStartLine}`, b.summary);
      w.setPosition({ lineNumber: b.anchorStartLine, column: 1 });
      ed.layoutContentWidget(w);
    }

    for (const [id, w] of summaryWidgetsRef.current.entries()) {
      if (nextIds.has(id)) continue;
      ed.removeContentWidget(w);
      summaryWidgetsRef.current.delete(id);
    }
  }, [props.breakouts]);

  useEffect(() => {
    const id = window.setInterval(() => {
      const now = Date.now();
      const idleMs = now - lastActivityRef.current;
      if (idleMs < 30000) return;
      if (now - lastIdleSentRef.current < 30000) return;
      lastIdleSentRef.current = now;
      props.onTelemetryEvent("idle", { idle_ms: idleMs });
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  function toMonacoRange(r: Range) {
    const m = monacoRef.current!;
    return new m.Range(r.startLine, r.startCol, r.endLine, r.endCol);
  }

  function getModel() {
    const ed = editorRef.current;
    return ed?.getModel() ?? null;
  }

  // ✅ Expose EditorAPI for actionPlayer
  useImperativeHandle(ref, () => ({
    revealLine(line: number) {
      const ed = editorRef.current;
      if (!ed) return;
      ed.revealLineInCenter(line);
    },
    setSelection(range: Range) {
      const ed = editorRef.current;
      const m = monacoRef.current;
      if (!ed || !m) return;
      const mr = toMonacoRange(range);
      ed.setSelection(mr);
      ed.revealRangeInCenter(mr);
    },
    deleteRange(range: Range) {
      const ed = editorRef.current;
      const m = monacoRef.current;
      const model = getModel();
      if (!ed || !m || !model) return;
      ed.executeEdits("agent", [{ range: toMonacoRange(range), text: "" }]);
    },
    async replaceRange(range: Range, text: string, typing: boolean, speedMs: number, onTypePos?: (p: { line: number; col: number }) => void) {
      const ed = editorRef.current;
      const m = monacoRef.current;
      const model = getModel();
      if (!ed || !m || !model) return;

      // replace all at once then type? 为了更像论文：先 delete，再逐字插入
      ed.executeEdits("agent", [{ range: toMonacoRange(range), text: "" }]);

      const start = { lineNumber: range.startLine, column: range.startCol };
      let startOffset = model.getOffsetAt(start);

      if (!typing) {
        ed.executeEdits("agent", [{ range: new m.Range(range.startLine, range.startCol, range.startLine, range.startCol), text }]);
        return;
      }

      for (let i = 0; i < text.length; i++) {
        const pos = model.getPositionAt(startOffset + i);
        ed.executeEdits("agent", [{ range: new m.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column), text: text[i] }]);
        onTypePos?.({ line: pos.lineNumber, col: pos.column + 1 });
        await sleep(speedMs);
      }
    },
    async insertAt(range: Range, text: string, typing: boolean, speedMs: number, onTypePos?: (p: { line: number; col: number }) => void) {
      const ed = editorRef.current;
      const m = monacoRef.current;
      const model = getModel();
      if (!ed || !m || !model) return;

      // insert at start of range
      const insertPos = { lineNumber: range.startLine, column: range.startCol };
      let startOffset = model.getOffsetAt(insertPos);

      if (!typing) {
        ed.executeEdits("agent", [{ range: new m.Range(range.startLine, range.startCol, range.startLine, range.startCol), text }]);
        return;
      }

      for (let i = 0; i < text.length; i++) {
        const pos = model.getPositionAt(startOffset + i);
        ed.executeEdits("agent", [{ range: new m.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column), text: text[i] }]);
        onTypePos?.({ line: pos.lineNumber, col: pos.column + 1 });
        await sleep(speedMs);
      }
    },
    highlightProvenance(range: Range, ttlMs: number) {
      const ed = editorRef.current;
      const m = monacoRef.current;
      if (!ed || !m) return;

      provDecoRef.current = ed.deltaDecorations(provDecoRef.current, [
        { range: toMonacoRange(range), options: { inlineClassName: "provenanceHighlight" } }
      ]);

      setTimeout(() => {
        const ed2 = editorRef.current;
        if (!ed2) return;
        provDecoRef.current = ed2.deltaDecorations(provDecoRef.current, []);
      }, ttlMs);
    },
    createBreakoutFromSelection() {
      const ed = editorRef.current;
      if (!ed) return;
      const sel = ed.getSelection();
      if (!sel || sel.isEmpty()) {
        console.log("No selection to create breakout from");
        return;
      }
      props.onCreateBreakoutFromSelection(sel.startLineNumber, sel.endLineNumber);
    },
    getInsertionTarget(preferred?: Range): InsertionTarget {
      const ed = editorRef.current;
      
      // 0. Explicit
      if (preferred) {
         return {
           range: preferred,
           kind: "explicit",
           position: { line: preferred.startLine, col: preferred.startCol }
         };
      }

      if (!ed) {
         // Fallback if no editor
         return {
           range: { startLine: 1, startCol: 1, endLine: 1, endCol: 1 },
           kind: "fallback",
           position: { line: 1, col: 1 }
         };
      }

      // 1. Selection
      const sel = ed.getSelection();
      if (sel && !sel.isEmpty()) {
        return {
          range: { startLine: sel.startLineNumber, startCol: sel.startColumn, endLine: sel.endLineNumber, endCol: sel.endColumn },
          kind: "selection",
          position: { line: sel.endLineNumber, col: sel.endColumn }
        };
      }

      // 2. Cursor
      const pos = ed.getPosition();
      if (pos) {
        return {
           range: { startLine: pos.lineNumber, startCol: pos.column, endLine: pos.lineNumber, endCol: pos.column },
           kind: "cursor",
           position: { line: pos.lineNumber, col: pos.column }
        };
      }

      // 3. Fallback
      return {
         range: { startLine: 1, startCol: 1, endLine: 1, endCol: 1 },
         kind: "fallback",
         position: { line: 1, col: 1 }
      };
    },
    getCursor() {
      const ed = editorRef.current;
      if (!ed) return null;
      const pos = ed.getPosition();
      if (!pos) return null;
      return { line: pos.lineNumber, col: pos.column };
    },
    getSelectionRange() {
      const ed = editorRef.current;
      if (!ed) return null;
      const sel = ed.getSelection();
      if (!sel) return null;
      return {
        start_line: sel.startLineNumber,
        start_col: sel.startColumn,
        end_line: sel.endLineNumber,
        end_col: sel.endColumn
      };
    }
  }), []);

  // ✅ Breakout anchor highlight + glyph markers
  useEffect(() => {
    const ed = editorRef.current;
    const m = monacoRef.current;
    if (!ed || !m) return;

    const anchorDecos = props.breakouts.map((b) => ({
      range: new m.Range(b.anchorStartLine, 1, b.anchorEndLine, 1),
      options: { isWholeLine: true, className: "breakoutAnchorLine" }
    }));

    breakoutDecoRef.current = ed.deltaDecorations(breakoutDecoRef.current, anchorDecos as any);

    const glyphDecos = props.breakouts.map((b) => ({
      range: new m.Range(b.anchorStartLine, 1, b.anchorStartLine, 1),
      options: {
        glyphMarginClassName: "breakoutGlyph",
        glyphMarginHoverMessage: { value: `Breakout: ${b.title}` }
      }
    }));

    glyphDecoRef.current = ed.deltaDecorations(glyphDecoRef.current, glyphDecos as any);
  }, [props.breakouts]);

  useEffect(() => {
    const ed = editorRef.current;
    const m = monacoRef.current;
    if (!ed || !m) return;

    const h = props.highlights;
    if (!h || !h.spans || h.spans.length === 0 || Date.now() > h.expiresAt) {
      diagDecoRef.current = ed.deltaDecorations(diagDecoRef.current, []);
      return;
    }

    const decos = h.spans.map((s: any) => {
      const lineStart = s.line_start ?? s.lineStart ?? s.start_line ?? s.startLine ?? 1;
      const lineEnd = s.line_end ?? s.lineEnd ?? s.end_line ?? s.endLine ?? lineStart;
      return {
        range: new m.Range(lineStart, 1, lineEnd, 1),
        options: { isWholeLine: true, className: "diagnosisHighlight" }
      };
    });

    diagDecoRef.current = ed.deltaDecorations(diagDecoRef.current, decos as any);

    const ttl = Math.max(0, h.expiresAt - Date.now());
    const t = window.setTimeout(() => {
      const ed2 = editorRef.current;
      if (!ed2) return;
      diagDecoRef.current = ed2.deltaDecorations(diagDecoRef.current, []);
    }, ttl);
    return () => window.clearTimeout(t);
  }, [props.highlights]);

  // ✅ AI widgets rendering from props.ai
  useEffect(() => {
    const ed = editorRef.current;
    if (!ed) return;

    const cursorW = aiCursorW.current;
    const caretW = aiCaretW.current;
    const bubbleW = aiBubbleW.current;

    if (cursorW) {
      cursorW.setPosition(props.ai.cursor ? { lineNumber: props.ai.cursor.line, column: props.ai.cursor.col } : null);
      cursorW.setLoading(props.ai.loading);
      ed.layoutContentWidget(cursorW);
    }
    if (caretW) {
      caretW.setPosition(props.ai.caret ? { lineNumber: props.ai.caret.line, column: props.ai.caret.col } : null);
      ed.layoutContentWidget(caretW);
    }
    if (bubbleW) {
      bubbleW.setPosition(props.ai.cursor ? { lineNumber: props.ai.cursor.line, column: props.ai.cursor.col } : null);
      if (props.ai.bubble) bubbleW.setBubble(props.ai.bubble.emoji ?? "", props.ai.bubble.text);
      ed.layoutContentWidget(bubbleW);
      (bubbleW.getDomNode() as HTMLElement).style.display = props.ai.bubble ? "block" : "none";
    }
  }, [props.ai]);

  // ✅ active breakout → reveal line
  useEffect(() => {
    const ed = editorRef.current;
    if (!ed) return;
    if (!props.activeBreakoutId) return;
    const b = props.breakouts.find((x) => x.id === props.activeBreakoutId);
    if (!b) return;
    ed.revealLineInCenter(b.anchorStartLine);
  }, [props.activeBreakoutId, props.breakouts]);

  // Breakout overlay positions
  const breakoutPositions = useMemo(() => {
    const ed = editorRef.current;
    const m = monacoRef.current;
    const map: Record<string, { top: number; visible: boolean }> = {};
    if (!ed || !m) return map;
    const layout = ed.getLayoutInfo();
    const height = layout.height;

    for (const b of props.breakouts) {
      if (!b.open) continue;
      const pos = ed.getScrolledVisiblePosition({ lineNumber: b.anchorStartLine, column: 1 });
      if (!pos) {
        map[b.id] = { top: 0, visible: false };
        continue;
      }
      const visible = pos.top > -40 && pos.top < height - 40;
      map[b.id] = { top: pos.top, visible };
    }
    return map;
  }, [props.breakouts, overlayTick]);

  return (
    <div className="editorWrap">
      <Editor
        height="100%"
        defaultLanguage="python"
        value={props.code}         // ✅ controlled: code state 不再为空
        onMount={onMount}
        onChange={(v) => props.onCodeChange(v ?? "")}
        theme="vs-dark"
      />

      <BreakoutOverlay
        breakouts={props.breakouts}
        positions={breakoutPositions}
        activeId={props.activeBreakoutId}
        onClose={props.onCloseBreakout}
        onFocus={props.onFocusBreakout}
        onSend={props.onSendBreakout}
        onPositionChange={props.onUpdateBreakoutPosition}
      />
    </div>
  );
});
