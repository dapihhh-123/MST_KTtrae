import { useMemo } from "react";
import type { OracleState } from "../../reducers/oracleReducer";

export default function OracleStatusBar({ state }: { state: OracleState }) {
  const statusColor = useMemo(() => {
    if (state.warning?.type === "error") return "red";
    if (state.warning?.type === "low_confidence") return "orange";
    if (state.stage === "tests_generated" || state.stage === "run_done") return "green";
    return "gray";
  }, [state.stage, state.warning]);

  const statusText = useMemo(() => {
    if (state.warning) return state.warning.message;
    switch (state.stage) {
      case "init": return "无任务";
      case "analyzing": return "正在分析需求...";
      case "awaiting_confirmation": return "发现歧义，等待确认";
      case "ready_no_tests": return "任务规格就绪";
      case "generating_tests": return "正在生成测试用例...";
      case "tests_generated": return "测试用例就绪";
      case "running": return "正在运行评测...";
      case "run_done": return "评测完成";
      default: return state.stage;
    }
  }, [state.stage, state.warning]);

  return (
    <div className="oracleStatusBar" style={{ borderLeft: `4px solid ${statusColor}` }}>
      <div className="statusMain">
        <span className="stageLabel">{statusText}</span>
        {state.currentVersionId && <span className="versionBadge">v{state.currentVersionId.slice(0, 6)}</span>}
      </div>
      {state.taskId && <div className="taskId">Task: {state.taskId.slice(0, 8)}...</div>}
      
      <style>{`
        .oracleStatusBar {
          background: #252526;
          padding: 8px 12px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 0.85rem;
          border-bottom: 1px solid #333;
        }
        .statusMain { display: flex; gap: 10px; align-items: center; }
        .stageLabel { font-weight: 500; color: #eee; }
        .versionBadge { background: #333; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.75rem; }
        .taskId { color: #888; font-family: monospace; font-size: 0.75rem; }
      `}</style>
    </div>
  );
}
