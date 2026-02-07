import { useState } from "react";
import type { OracleState } from "../../reducers/oracleReducer";

export default function DebugSection({ state }: { state: OracleState }) {
  const [filter, setFilter] = useState("");
  
  const logs = state.apiLog.filter(l => l.endpoint.includes(filter));

  return (
    <div>
      <h3 className="sectionTitle">调试与日志 (Debug & Logs)</h3>
      
      <div className="oracleFormGroup">
          <input 
            className="oracleInput" 
            placeholder="过滤 Endpoint..." 
            value={filter} 
            onChange={e => setFilter(e.target.value)} 
          />
      </div>

      <div className="logList">
          {logs.map((l, i) => (
              <LogItem key={i} entry={l} />
          ))}
      </div>
    </div>
  );
}

function LogItem({ entry }: { entry: any }) {
    const [expanded, setExpanded] = useState(false);
    
    return (
        <div style={{ background: "#252526", marginBottom: "4px", fontSize: "0.8rem", fontFamily: "monospace" }}>
            <div 
                onClick={() => setExpanded(!expanded)}
                style={{ padding: "6px", cursor: "pointer", display: "flex", justifyContent: "space-between", color: entry.status >= 400 ? "#f44336" : "#ddd" }}
            >
                <span>{entry.endpoint}</span>
                <span>{entry.status} ({entry.durationMs}ms)</span>
            </div>
            {expanded && (
                <div style={{ padding: "6px", borderTop: "1px solid #333", background: "#1e1e1e" }}>
                    <div style={{ color: "#aaa", marginBottom: "2px" }}>Request:</div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: "#9cdcfe" }}>{JSON.stringify(entry.req, null, 2)}</pre>
                    <div style={{ color: "#aaa", margin: "6px 0 2px 0" }}>Response:</div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: "#ce9178" }}>{JSON.stringify(entry.res, null, 2)}</pre>
                </div>
            )}
        </div>
    );
}
