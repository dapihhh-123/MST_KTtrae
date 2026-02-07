import { useState, useEffect } from "react";
import { api } from "../../services/api";
import type { OracleState, OracleAction } from "../../reducers/oracleReducer";
import type { SpecBody, Ambiguity } from "../../types/oracle";

export default function SpecSection({ state, dispatch }: { state: OracleState; dispatch: React.Dispatch<OracleAction> }) {
  const [desc, setDesc] = useState("");
  const [lang, setLang] = useState("python");
  const [deliv, setDeliv] = useState<"function"|"cli"|"script">("function");
  const [debugMock, setDebugMock] = useState(false);

  // Load spec details if version switched
  useEffect(() => {
    if (state.currentVersionId && !state.specResponse) {
        // We need to fetch details for this version if not already in state
        // For simplicity in this demo, let's assume we fetch it
        api.oracleGetVersion(state.currentVersionId).then(res => {
            dispatch({ type: "VERSION_DETAILS_LOADED", payload: res });
        });
    }
  }, [state.currentVersionId]);

  function handleGenerate() {
    if (!state.taskId) return;
    dispatch({ type: "SET_LOADING", payload: { key: "spec", value: true } });
    
    const body: SpecBody = {
        task_description: desc,
        language: lang,
        deliverable_type: deliv,
        debug_invalid_mock: debugMock
    };

    api.oracleGenerateSpec(state.taskId, body)
       .then(res => {
           dispatch({ type: "SPEC_GENERATED", payload: res });
       })
       .catch(e => {
           dispatch({ type: "SET_WARNING", payload: { type: "error", message: String(e) } });
       })
       .finally(() => {
           dispatch({ type: "SET_LOADING", payload: { key: "spec", value: false } });
       });
  }

  function handleConfirm() {
      if (!state.currentVersionId) return;
      dispatch({ type: "SET_LOADING", payload: { key: "confirm", value: true } });
      api.oracleConfirm(state.currentVersionId, { selections: state.ambiguitySelections })
         .then(res => {
             dispatch({ type: "CONFIRMED", payload: res });
         })
         .catch(e => {
            dispatch({ type: "SET_WARNING", payload: { type: "error", message: String(e) } });
         })
         .finally(() => {
            dispatch({ type: "SET_LOADING", payload: { key: "confirm", value: false } });
         });
  }

  const spec = state.specResponse?.spec_summary;
  const ambiguities = state.specResponse?.ambiguities || [];
  const needsConfirm = ambiguities.length > 0 && (state.stage === "awaiting_confirmation");

  return (
    <div>
      <h3 className="sectionTitle">任务规格 (Specification)</h3>

      {!state.taskId && <div className="card" style={{ color: "orange" }}>请先创建一个任务。</div>}

      <div className="card">
        <div className="oracleFormGroup">
          <label>任务描述</label>
          <textarea 
            className="oracleTextarea" 
            value={desc} 
            onChange={e => setDesc(e.target.value)}
            placeholder="请清晰描述您的任务需求..."
          />
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
           <div className="oracleFormGroup" style={{ flex: 1 }}>
             <label>编程语言</label>
             <select className="oracleSelect" value={lang} onChange={e => setLang(e.target.value)}>
               <option value="python">Python</option>
               <option value="javascript">JavaScript</option>
             </select>
           </div>
           <div className="oracleFormGroup" style={{ flex: 1 }}>
             <label>交付类型</label>
             <select className="oracleSelect" value={deliv} onChange={e => setDeliv(e.target.value as any)}>
               <option value="function">函数 (Function)</option>
               <option value="cli">命令行工具 (CLI)</option>
               <option value="script">脚本 (Script)</option>
             </select>
           </div>
        </div>
        <div className="oracleFormGroup">
           <label>
             <input type="checkbox" checked={debugMock} onChange={e => setDebugMock(e.target.checked)} /> 使用 Mock LLM (调试用)
           </label>
        </div>
        <button 
            className="oracleBtn" 
            onClick={handleGenerate} 
            disabled={!state.taskId || state.loadingFlags.spec || !desc.trim()}
        >
            {state.loadingFlags.spec ? "正在分析..." : "生成 / 更新规格"}
        </button>
      </div>

      {spec && (
          <div className="card" style={{ borderColor: "#007acc" }}>
              <h4>规格摘要</h4>
              <p><strong>目标:</strong> {spec.goal_one_liner}</p>
              {spec.constraints && (
                  <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", marginTop: "8px" }}>
                      {spec.constraints.map((c, i) => (
                          <span key={i} style={{ background: "#333", padding: "2px 6px", borderRadius: "4px", fontSize: "0.8rem" }}>{c}</span>
                      ))}
                  </div>
              )}
              {spec.signature && (
                  <div style={{ marginTop: "10px", fontFamily: "monospace", background: "#111", padding: "8px" }}>
                      {spec.signature.function_name}({spec.signature.args?.map((a: any) => typeof a === 'string' ? a : a.name).join(", ")}) 
                      {spec.signature.returns && spec.signature.returns !== "Any" && ` -> ${spec.signature.returns}`}
                  </div>
              )}
          </div>
      )}

      {ambiguities.length > 0 && (
          <div className="card" style={{ borderColor: "orange" }}>
              <h4>检测到需求歧义</h4>
              {ambiguities.map(amb => (
                  <div key={amb.ambiguity_id} style={{ marginBottom: "16px" }}>
                      <p style={{ marginBottom: "8px" }}>{amb.description}</p>
                      {amb.choices.map(c => (
                          <label key={c.choice_id} style={{ display: "block", padding: "4px", cursor: "pointer" }}>
                              <input 
                                type="radio" 
                                name={amb.ambiguity_id} 
                                value={c.choice_id}
                                checked={state.ambiguitySelections[amb.ambiguity_id] === c.choice_id}
                                onChange={() => dispatch({ type: "AMBIGUITY_SELECT", payload: { id: amb.ambiguity_id, choiceId: c.choice_id } })}
                                disabled={state.stage !== "awaiting_confirmation"}
                              /> 
                              <span style={{ marginLeft: "8px" }}>{c.text}</span>
                          </label>
                      ))}
                  </div>
              ))}
              {needsConfirm && (
                  <button 
                    className="oracleBtn" 
                    onClick={handleConfirm}
                    disabled={Object.keys(state.ambiguitySelections).length < ambiguities.length || state.loadingFlags.confirm}
                  >
                      {state.loadingFlags.confirm ? "正在确认..." : "确认选择"}
                  </button>
              )}
          </div>
      )}
    </div>
  );
}
