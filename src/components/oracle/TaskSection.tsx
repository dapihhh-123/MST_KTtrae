import { useState, useEffect } from "react";
import { api } from "../../services/api";
import type { OracleState, OracleAction } from "../../reducers/oracleReducer";

export default function TaskSection({ state, dispatch }: { state: OracleState; dispatch: React.Dispatch<OracleAction> }) {
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    // If we have a task ID but no versions loaded, load them
    if (state.taskId && state.versions.length === 0 && state.stage === "init") {
       api.oracleGetTask(state.taskId).then(res => {
           dispatch({ type: "TASK_LOADED", payload: { taskId: res.task_id, versions: res.versions } });
       }).catch(() => {});
    }
  }, [state.taskId]);

  function handleCreateTask() {
    setCreating(true);
    dispatch({ type: "SET_LOADING", payload: { key: "createTask", value: true } });
    api.oracleCreateTask()
      .then(res => {
        dispatch({ type: "TASK_CREATED", payload: res });
      })
      .catch(e => {
        dispatch({ type: "SET_WARNING", payload: { type: "error", message: String(e) } });
      })
      .finally(() => {
        setCreating(false);
        dispatch({ type: "SET_LOADING", payload: { key: "createTask", value: false } });
      });
  }

  return (
    <div>
      <h3 className="sectionTitle">任务管理</h3>
      
      {!state.taskId ? (
        <div className="card" style={{ textAlign: "center", padding: "40px 20px" }}>
          <p>当前没有活动任务。</p>
          <button className="oracleBtn" onClick={handleCreateTask} disabled={creating}>
            {creating ? "正在创建..." : "创建新任务"}
          </button>
        </div>
      ) : (
        <div>
          <div className="card">
            <div style={{ fontSize: "0.9rem", color: "#aaa", marginBottom: "8px" }}>当前任务 ID</div>
            <div style={{ fontFamily: "monospace", userSelect: "all", background: "#333", padding: "4px" }}>
              {state.taskId}
            </div>
          </div>

          <h4 style={{ marginTop: "20px", marginBottom: "10px" }}>版本历史</h4>
          {state.versions.length === 0 ? (
            <div style={{ color: "#888", fontStyle: "italic" }}>暂无版本。请前往“规格”页签创建。</div>
          ) : (
            <div className="versionList">
              {state.versions.slice().reverse().map(v => (
                <div 
                  key={v.versionId} 
                  className={`card versionRow ${state.currentVersionId === v.versionId ? "active" : ""}`}
                  onClick={() => dispatch({ type: "SWITCH_VERSION", payload: v.versionId })}
                  style={{ cursor: "pointer", borderLeft: state.currentVersionId === v.versionId ? "3px solid #007acc" : "1px solid #333" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                     <span style={{ fontWeight: "bold" }}>v{v.versionId.slice(0, 6)}</span>
                     <span style={{ fontSize: "0.8rem", color: "#aaa" }}>{new Date(v.createdAt).toLocaleTimeString()}</span>
                  </div>
                  <div style={{ fontSize: "0.8rem", marginTop: "4px" }}>
                    状态: <span style={{ color: v.status === "ready" ? "#8fd" : "#ddd" }}>{v.status}</span>
                  </div>
                  {v.confidence !== undefined && (
                     <div style={{ fontSize: "0.8rem" }}>置信度: {(v.confidence * 100).toFixed(0)}%</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
