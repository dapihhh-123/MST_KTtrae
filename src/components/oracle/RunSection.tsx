import { useState } from "react";
import { api } from "../../services/api";
import type { OracleState, OracleAction } from "../../reducers/oracleReducer";

export default function RunSection({ state, dispatch, getSnapshot }: { 
    state: OracleState; 
    dispatch: React.Dispatch<OracleAction>; 
    getSnapshot: () => { files: Record<string, string>; entrypoint: string } 
}) {
  const [timeout, setTimeoutSec] = useState(2.5);

  function handleRun() {
      if (!state.currentVersionId) return;
      const snapshot = getSnapshot();
      const code = snapshot.files[snapshot.entrypoint] || "";
      
      if (!code && Object.keys(snapshot.files).length === 0) {
          alert("No code in workspace!");
          return;
      }
      
      dispatch({ type: "SET_LOADING", payload: { key: "run", value: true } });
      dispatch({ type: "RUN_STARTED" });

      api.oracleRun(state.currentVersionId, {
          code_text: code, // Legacy support
          workspace_files: snapshot.files,
          entrypoint: snapshot.entrypoint,
          timeout_sec: timeout
      })
      .then(res => {
          dispatch({ type: "RUN_DONE", payload: res });
      })
      .catch(e => {
          dispatch({ type: "SET_WARNING", payload: { type: "error", message: String(e) } });
      })
      .finally(() => {
          dispatch({ type: "SET_LOADING", payload: { key: "run", value: false } });
      });
  }

  const history = state.runHistory.filter(h => h.versionId === state.currentVersionId);
  const latestRun = history[0]?.run;

  return (
    <div>
      <h3 className="sectionTitle">代码评测 (Evaluate Code)</h3>

      <div className="card">
         <div className="oracleFormGroup">
             <label>超时时间 (秒)</label>
             <input type="number" className="oracleInput" value={timeout} onChange={e => setTimeoutSec(parseFloat(e.target.value))} step={0.5} />
         </div>
         <button 
            className="oracleBtn primary" 
            onClick={handleRun}
            disabled={state.stage !== "tests_generated" && state.stage !== "run_done" || state.loadingFlags.run}
            style={{ width: "100%", padding: "10px" }}
         >
             {state.loadingFlags.run ? "正在评测..." : "▶ 运行评测"}
         </button>
      </div>

      {latestRun && (
          <div className="card" style={{ borderColor: latestRun.pass_rate === 1 ? "#4caf50" : "#f44336" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                  <h4>评测结果</h4>
                  <span style={{ fontSize: "1.2rem", fontWeight: "bold", color: latestRun.pass_rate === 1 ? "#4caf50" : "#f44336" }}>
                      {(latestRun.pass_rate * 100).toFixed(0)}%
                  </span>
              </div>
              <div style={{ height: "6px", background: "#333", borderRadius: "3px", overflow: "hidden", marginBottom: "12px" }}>
                  <div style={{ width: `${latestRun.pass_rate * 100}%`, background: latestRun.pass_rate === 1 ? "#4caf50" : "#f44336", height: "100%" }}></div>
              </div>
              <div style={{ display: "flex", gap: "12px", fontSize: "0.9rem" }}>
                  <span style={{ color: "#4caf50" }}>通过: {latestRun.passed}</span>
                  <span style={{ color: "#f44336" }}>失败: {latestRun.failed}</span>
              </div>

              {latestRun.failures_summary.length > 0 && (
                  <div style={{ marginTop: "12px", background: "#1e1e1e", padding: "8px", borderRadius: "4px" }}>
                      <h5 style={{ margin: "0 0 8px 0" }}>失败详情</h5>
                      {latestRun.failures_summary.map((f, i) => (
                          <div key={i} style={{ marginBottom: "8px", fontSize: "0.85rem", borderBottom: "1px solid #333", paddingBottom: "4px" }}>
                              <div style={{ fontWeight: "bold", color: "#f44336" }}>{f.test_name} {f.hidden && "(隐藏用例)"}</div>
                              {f.error ? (
                                  <div style={{ color: "#ffab91" }}>错误: {f.error}</div>
                              ) : (
                                  <>
                                    <div>预期: {String(f.expected)}</div>
                                    <div>实际: {String(f.got)}</div>
                                  </>
                              )}
                          </div>
                      ))}
                  </div>
              )}
          </div>
      )}

      {history.length > 1 && (
          <div style={{ marginTop: "20px" }}>
              <h4 style={{ fontSize: "0.9rem", color: "#888" }}>历史记录</h4>
              {history.slice(1, 5).map((h, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #333", fontSize: "0.85rem" }}>
                      <span>{new Date(h.ts).toLocaleTimeString()}</span>
                      <span style={{ color: h.run.pass_rate === 1 ? "#4caf50" : "#aaa" }}>{(h.run.pass_rate * 100).toFixed(0)}%</span>
                  </div>
              ))}
          </div>
      )}
    </div>
  );
}
