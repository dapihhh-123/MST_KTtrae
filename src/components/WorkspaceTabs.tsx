
import { WorkspaceState } from "../types/workspace";

export default function WorkspaceTabs({ workspace, dispatch }: { workspace: WorkspaceState; dispatch: React.Dispatch<any> }) {
    return (
        <div style={{ display: "flex", background: "#252526", overflowX: "auto", borderBottom: "1px solid #1e1e1e" }}>
            {workspace.openFiles.map(path => (
                <div 
                    key={path}
                    onClick={() => dispatch({ type: "FILE_SET_ACTIVE", payload: { path } })}
                    style={{ 
                        padding: "8px 12px", 
                        background: workspace.activeFile === path ? "#1e1e1e" : "#2d2d2d",
                        color: workspace.activeFile === path ? "#fff" : "#999",
                        borderRight: "1px solid #1e1e1e",
                        borderTop: workspace.activeFile === path ? "1px solid #007acc" : "1px solid transparent",
                        cursor: "pointer",
                        fontSize: "0.9rem",
                        display: "flex",
                        alignItems: "center",
                        minWidth: "100px",
                        maxWidth: "200px"
                    }}
                    title={path}
                >
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{path}</span>
                    <button 
                        onClick={(e) => { e.stopPropagation(); dispatch({ type: "FILE_CLOSE", payload: { path } }) }}
                        style={{ marginLeft: "8px", border: "none", background: "none", color: "inherit", cursor: "pointer", opacity: 0.7 }}
                    >
                        ×
                    </button>
                </div>
            ))}
        </div>
    );
}
