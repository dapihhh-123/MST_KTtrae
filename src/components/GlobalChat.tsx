import { useState } from "react";
import type { GlobalThread } from "../types";
import { makeMessageKey } from "../utils/stableKey";

export default function GlobalChat(props: {
  collapsed: boolean;
  blurred: boolean;
  threads: GlobalThread[];
  onToggleCollapsePanel: () => void;
  onSend: (threadId: string, msg: any) => void;
  onToggleThread: (threadId: string) => void;
  onNavigateToBreakout: (breakoutId: string) => void;
  onSummarizeThread: (threadId: string) => void;
}) {
  const [input, setInput] = useState("");

  if (props.collapsed) {
    return (
      <div className="globalChat collapsed" onClick={props.onToggleCollapsePanel}>
        <div style={{ transform: "rotate(-90deg)", whiteSpace: "nowrap" }}>Global Chat</div>
      </div>
    );
  }

  const activeThread = props.threads.find(t => t.kind === "topic"); // simplify: just use the first topic thread

  const handleSend = () => {
    if (!input.trim() || !activeThread) return;
    
    // Task 3: Generate client_id
    const clientId = crypto.randomUUID();

    props.onSend(activeThread.id, {
      id: `temp_${clientId}`, // Temporary ID until server response
      client_id: clientId,
      role: "user",
      content: input,
      createdAt: Date.now()
    });
    setInput("");
  };

  return (
    <div className={`globalChat ${props.blurred ? "blurred" : ""}`}>
      <div className="chatHeader">
        <h3>Global Chat</h3>
      </div>
      
      <div className="chatBody">
        {props.threads.map(thread => (
          <div key={thread.id} className={`threadItem ${thread.kind}`}>
            {thread.kind === "breakoutSummary" ? (
              <div className="collapsedCard">
                <div className="titleRow">
                  <div className="title">{thread.title}</div>
                  <button 
                    className="smallBtn"
                    onClick={() => thread.breakoutId && props.onNavigateToBreakout(thread.breakoutId)}
                  >
                    View in editor →
                  </button>
                </div>
                <div className="summary">{thread.summary}</div>
              </div>
            ) : (
              // Topic thread
              <div className="topicThread">
                <div className="threadHeader">
                  <div className="threadMeta">
                    <span className="badge">topic</span>
                    <span className="title">{thread.title}</span>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="smallBtn" onClick={() => props.onSummarizeThread(thread.id)}>Summarize</button>
                    <button className="smallBtn" onClick={() => props.onToggleThread(thread.id)}>
                      {thread.collapsed ? "Expand" : "Collapse"}
                    </button>
                  </div>
                </div>
                
                <div className="threadSummary">{thread.summary}</div>
                
                {!thread.collapsed && (
                  <div className="messageList">
                    {thread.messages?.map(msg => {
                      const key = makeMessageKey("global", thread.id, msg);
                      const ts = msg.createdAt ?? msg.created_at ?? Date.now();
                      // Task 1: Debug Log
                      // console.log("render key", key, msg);
                      return (
                        <div key={key} className={`msg ${msg.role}`}>
                           <div className="meta">
                             <span>{msg.role}</span>
                             <span>{new Date(ts).toLocaleTimeString()}</span>
                           </div>
                          <div className="bubble">{msg.content}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="chatInputArea">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
      </div>
    </div>
  );
}
