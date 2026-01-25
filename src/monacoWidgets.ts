import * as monaco from "monaco-editor";

type WidgetKind = "cursor" | "caret" | "bubble";

export class AIPresenceWidget implements monaco.editor.IContentWidget {
  private dom: HTMLDivElement;
  private pos: monaco.IPosition | null = null;

  constructor(private id: string, private kind: WidgetKind) {
    this.dom = document.createElement("div");
    this.dom.className = "aiWidget";

    if (kind === "cursor") {
      const dot = document.createElement("div");
      dot.className = "aiCursorDot";
      this.dom.appendChild(dot);
    } else if (kind === "caret") {
      const bar = document.createElement("div");
      bar.className = "aiCaretBar";
      this.dom.appendChild(bar);
    } else {
      const bubble = document.createElement("div");
      bubble.className = "aiBubble";
      bubble.textContent = "🤔 Thinking...";
      this.dom.appendChild(bubble);
    }
  }

  getId(): string {
    return this.id;
  }

  getDomNode(): HTMLElement {
    return this.dom;
  }

  getPosition(): monaco.editor.IContentWidgetPosition | null {
    if (!this.pos) return null;
    return {
      position: this.pos,
      preference: [monaco.editor.ContentWidgetPositionPreference.ABOVE]
    };
  }

  setPosition(pos: monaco.IPosition | null) {
    this.pos = pos;
  }

  setLoading(loading: boolean) {
    if (this.kind !== "cursor") return;
    this.dom.classList.toggle("aiLoading", loading);
  }

  setBubble(emoji: string, text: string) {
    if (this.kind !== "bubble") return;
    const bubble = this.dom.firstElementChild as HTMLDivElement | null;
    if (!bubble) return;
    bubble.textContent = `${emoji} ${text}`;
  }
}

export class BreakoutSummaryWidget implements monaco.editor.IContentWidget {
  private dom: HTMLDivElement;
  private pos: monaco.IPosition | null = null;

  constructor(
    private id: string,
    private onClick: () => void
  ) {
    this.dom = document.createElement("div");
    this.dom.className = "breakoutSummaryWidget";
    this.dom.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.onClick();
    });
  }

  getId(): string {
    return this.id;
  }

  getDomNode(): HTMLElement {
    return this.dom;
  }

  getPosition(): monaco.editor.IContentWidgetPosition | null {
    if (!this.pos) return null;
    return {
      position: this.pos,
      preference: [monaco.editor.ContentWidgetPositionPreference.ABOVE]
    };
  }

  setPosition(pos: monaco.IPosition | null) {
    this.pos = pos;
  }

  setContent(title: string, summary: string) {
    this.dom.innerHTML = "";
    const header = document.createElement("div");
    header.className = "breakoutSummaryTitle";
    header.textContent = title;
    const body = document.createElement("div");
    body.className = "breakoutSummaryBody";
    body.textContent = summary;
    this.dom.appendChild(header);
    this.dom.appendChild(body);
  }
}
