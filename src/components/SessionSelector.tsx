import { useState, useEffect } from "react";
import { api } from "../services/api";
import type { Session } from "../types";

export default function SessionSelector(props: { onSelect: (sessionId: string) => void }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadSessions();
  }, []);

  function loadSessions() {
    setLoading(true);
    api.getSessionsPublic()
      .then(setSessions)
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }

  function handleCreate() {
    if (!newTitle.trim()) return;
    setCreating(true);
    // Assuming default workspace for now, or fetch workspaces first.
    // Since initSession used a default workspace creation logic, let's try to get workspaces first.
    // Or we can rely on initSession logic to ensure workspace exists?
    // Let's first ensure we have a workspace ID.
    // For simplicity, let's list workspaces, if empty create one.
    
    // Quick hack: Use a hardcoded "default" check or fetch workspaces
    fetch("/api/workspaces").then(r => r.json()).then(wsList => {
        let wsId = wsList[0]?.id;
        if (!wsId) {
             // Create one
             return fetch("/api/workspaces", { 
                 method: "POST", 
                 headers: {"Content-Type": "application/json"},
                 body: JSON.stringify({ name: "Default Workspace" })
             }).then(r => r.json()).then(w => w.id);
        }
        return wsId;
    }).then(wsId => {
        return api.createSession(newTitle, wsId);
    }).then((newSess) => {
        setSessions([newSess, ...sessions]);
        setNewTitle("");
        props.onSelect(newSess.id);
    }).catch(e => {
        console.error("Create failed", e);
        alert("Failed to create session");
    }).finally(() => setCreating(false));
  }

  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!confirm("Delete this session?")) return;
    api.deleteSession(id).then(() => {
        setSessions(sessions.filter(s => s.id !== id));
    });
  }

  return (
    <div className="sessionSelector">
      <div className="selectorCard">
        <h2>Select a Session</h2>
        
        <div className="createRow">
          <input 
            type="text" 
            placeholder="New Session Title..." 
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
            disabled={creating}
          />
          <button className="btn primary" onClick={handleCreate} disabled={creating || !newTitle.trim()}>
            {creating ? "Creating..." : "Create New"}
          </button>
        </div>

        <div className="sessionList">
          {loading ? (
            <div className="loading">Loading sessions...</div>
          ) : sessions.length === 0 ? (
            <div className="empty">No sessions found. Create one above.</div>
          ) : (
            sessions.map(s => (
              <div key={s.id} className="sessionRow" onClick={() => props.onSelect(s.id)}>
                <div className="sessionInfo">
                  <div className="sessionTitle">{s.title || "Untitled Session"}</div>
                  <div className="sessionMeta">
                    <span className="pill">{s.language}</span>
                    <span className="date">{new Date(s.updated_at * 1000).toLocaleString()}</span>
                  </div>
                </div>
                <button className="btn ghost deleteBtn" onClick={(e) => handleDelete(e, s.id)}>
                  🗑️
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <style>{`
        .sessionSelector {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100vh;
          background: #1e1e1e;
          color: #eee;
        }
        .selectorCard {
          width: 500px;
          background: #252526;
          padding: 24px;
          border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.3);
          border: 1px solid #333;
        }
        h2 { margin-top: 0; margin-bottom: 20px; font-weight: 500; }
        .createRow {
          display: flex;
          gap: 10px;
          margin-bottom: 20px;
        }
        .createRow input {
          flex: 1;
          background: #3c3c3c;
          border: 1px solid #3c3c3c;
          color: white;
          padding: 8px 12px;
          border-radius: 4px;
        }
        .createRow input:focus { outline: none; border-color: #007acc; }
        .sessionList {
          max-height: 400px;
          overflow-y: auto;
          border-top: 1px solid #333;
        }
        .sessionRow {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          border-bottom: 1px solid #333;
          cursor: pointer;
          transition: background 0.2s;
        }
        .sessionRow:hover { background: #2a2d2e; }
        .sessionTitle { font-weight: bold; margin-bottom: 4px; }
        .sessionMeta { font-size: 0.85em; color: #aaa; display: flex; gap: 8px; align-items: center; }
        .deleteBtn { color: #888; padding: 4px 8px; }
        .deleteBtn:hover { color: #f44; background: rgba(255,0,0,0.1); }
        .loading, .empty { padding: 20px; text-align: center; color: #888; }
      `}</style>
    </div>
  );
}