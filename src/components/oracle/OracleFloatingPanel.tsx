import { useState, useReducer, useEffect } from "react";
import { oracleReducer, initialOracleState } from "../../reducers/oracleReducer";
import { setApiLogger } from "../../services/api";
import OracleStatusBar from "./OracleStatusBar";
import TaskSection from "./TaskSection";
import SpecSection from "./SpecSection";
import TestsSection from "./TestsSection";
import RunSection from "./RunSection";
import DebugSection from "./DebugSection";
import { setOracleVersionIdForPSW } from "../../psw/oracle_integration";

import "./OraclePanel.css"; // We'll create this CSS file

export default function OracleFloatingPanel(props: { 
    onClose: () => void; 
    getSnapshot: () => { files: Record<string, string>; entrypoint: string } 
}) {
  const [state, dispatch] = useReducer(oracleReducer, initialOracleState);
  const [activeTab, setActiveTab] = useState<"task" | "spec" | "tests" | "run" | "debug">("task");

  // Hook up logging
  useEffect(() => {
    setApiLogger((entry) => dispatch({ type: "LOG_API", payload: entry }));
    return () => setApiLogger(null);
  }, []);


  useEffect(() => {
    setOracleVersionIdForPSW(state.currentVersionId || null);
  }, [state.currentVersionId]);

  // Auto-switch tabs based on stage
  useEffect(() => {
    if (state.stage === "awaiting_confirmation") setActiveTab("spec");
    if (state.stage === "ready_no_tests" && activeTab === "task") setActiveTab("spec");
    if (state.stage === "tests_generated" && activeTab === "spec") setActiveTab("tests");
    if (state.stage === "run_done") setActiveTab("run");
  }, [state.stage]);

  return (
    <div className="oraclePanel">
      <div className="oracleHeader">
        <div className="dragHandle">任务预言机 (Task Oracle)</div>
        <button className="closeBtn" onClick={props.onClose}>×</button>
      </div>

      <OracleStatusBar state={state} />

      <div className="oracleBody">
        <div className="oracleNav">
          <button className={activeTab === "task" ? "active" : ""} onClick={() => setActiveTab("task")}>任务</button>
          <button className={activeTab === "spec" ? "active" : ""} onClick={() => setActiveTab("spec")}>规格</button>
          <button className={activeTab === "tests" ? "active" : ""} onClick={() => setActiveTab("tests")}>测试</button>
          <button className={activeTab === "run" ? "active" : ""} onClick={() => setActiveTab("run")}>评测</button>
          <button className={activeTab === "debug" ? "active" : ""} onClick={() => setActiveTab("debug")}>调试</button>
        </div>

        <div className="oracleContent">
          {activeTab === "task" && <TaskSection state={state} dispatch={dispatch} />}
          {activeTab === "spec" && <SpecSection state={state} dispatch={dispatch} />}
          {activeTab === "tests" && <TestsSection state={state} dispatch={dispatch} />}
          {activeTab === "run" && <RunSection state={state} dispatch={dispatch} getSnapshot={props.getSnapshot} />}
          {activeTab === "debug" && <DebugSection state={state} />}
        </div>
      </div>
    </div>
  );
}
