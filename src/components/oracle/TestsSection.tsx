import { useState } from "react";
import { api } from "../../services/api";
import type { OracleState, OracleAction } from "../../reducers/oracleReducer";
import type { GenerateTestsBody } from "../../types/oracle";

export default function TestsSection({ state, dispatch }: { state: OracleState; dispatch: React.Dispatch<OracleAction> }) {
  const [publicCount, setPublicCount] = useState(3);
  const [hiddenCount, setHiddenCount] = useState(5);

  function handleGenerateTests() {
      if (!state.currentVersionId) return;
      dispatch({ type: "SET_LOADING", payload: { key: "tests", value: true } });
      
      const body: GenerateTestsBody = {
          public_examples_count: publicCount,
          hidden_tests_count: hiddenCount
      };

      api.oracleGenerateTests(state.currentVersionId, body)
         .then(res => {
             dispatch({ type: "TESTS_GENERATED", payload: res });
         })
         .catch(e => {
            dispatch({ type: "SET_WARNING", payload: { type: "error", message: String(e) } });
         })
         .finally(() => {
            dispatch({ type: "SET_LOADING", payload: { key: "tests", value: false } });
         });
  }

  const isReady = state.stage === "ready_no_tests" || state.stage === "tests_generated" || state.stage === "run_done";
  const tests = state.testsResponse;

  return (
    <div>
      <h3 className="sectionTitle">测试用例</h3>

      <div className="card">
         <div style={{ display: "flex", gap: "10px" }}>
             <div className="oracleFormGroup" style={{ flex: 1 }}>
                 <label>公开示例数</label>
                 <input type="number" className="oracleInput" value={publicCount} onChange={e => setPublicCount(parseInt(e.target.value))} min={1} max={10} />
             </div>
             <div className="oracleFormGroup" style={{ flex: 1 }}>
                 <label>隐藏测试数</label>
                 <input type="number" className="oracleInput" value={hiddenCount} onChange={e => setHiddenCount(parseInt(e.target.value))} min={1} max={50} />
             </div>
         </div>
         <button 
            className="oracleBtn" 
            onClick={handleGenerateTests}
            disabled={!isReady || state.loadingFlags.tests}
         >
             {state.loadingFlags.tests ? "正在生成测试..." : "生成测试用例"}
         </button>
      </div>

      {tests && (
          <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "10px" }}>
                  <h4>已生成测试套件</h4>
                  <span style={{ fontSize: "0.8rem", color: "#aaa" }}>置信度: {(tests.oracle_confidence * 100).toFixed(0)}%</span>
              </div>
              <p>隐藏测试数: <strong>{tests.hidden_tests_count}</strong> (保密)</p>
              
              <h5 style={{ marginTop: "12px", marginBottom: "8px" }}>公开示例预览</h5>
              <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                      <thead>
                          <tr style={{ borderBottom: "1px solid #444", textAlign: "left" }}>
                              <th style={{ padding: "4px" }}>输入 (Input)</th>
                              <th style={{ padding: "4px" }}>预期 (Expected)</th>
                          </tr>
                      </thead>
                      <tbody>
                          {tests.public_examples_preview.map((t, i) => (
                              <tr key={i} style={{ borderBottom: "1px solid #333" }}>
                                  <td style={{ padding: "4px", fontFamily: "monospace", color: "#ce9178" }}>{JSON.stringify(t.input)}</td>
                                  <td style={{ padding: "4px", fontFamily: "monospace", color: "#b5cea8" }}>{JSON.stringify(t.expected)}</td>
                              </tr>
                          ))}
                      </tbody>
                  </table>
              </div>
          </div>
      )}
    </div>
  );
}
