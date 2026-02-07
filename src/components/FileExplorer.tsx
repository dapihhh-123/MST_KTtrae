
import { useState, useMemo, useEffect, useRef } from "react";
import { WorkspaceState } from "../types/workspace";

type TreeNode = {
    name: string;
    path: string;
    kind: "file" | "folder";
    children?: Record<string, TreeNode>;
};

function buildTree(files: Record<string, string>): TreeNode {
    const root: TreeNode = { name: "", path: "", kind: "folder", children: {} };
    
    Object.keys(files).forEach(path => {
        const parts = path.split("/");
        let current = root;
        let currentPath = "";
        
        parts.forEach((part, index) => {
            const isLast = index === parts.length - 1;
            currentPath = currentPath ? `${currentPath}/${part}` : part;
            
            if (!current.children) current.children = {};
            
            if (!current.children[part]) {
                current.children[part] = {
                    name: part,
                    path: currentPath,
                    kind: isLast ? "file" : "folder",
                    children: isLast ? undefined : {}
                };
            } else {
                // Conflict handling: if existing node is file but we need folder (e.g. "a" vs "a/b")
                // In our flat map, "a" and "a/b" implies "a" is a file content.
                // We treat it as file. The children will be ignored by renderNode if kind is file.
            }
            current = current.children[part];
        });
    });
    
    return root;
}

const FileIcon = ({ name }: { name: string }) => {
    if (name.endsWith(".py")) return <span style={{ marginRight: "6px" }}>🐍</span>;
    if (name.endsWith(".json")) return <span style={{ marginRight: "6px" }}>{}</span>;
    if (name.endsWith(".md")) return <span style={{ marginRight: "6px" }}>📝</span>;
    if (name.endsWith(".txt")) return <span style={{ marginRight: "6px" }}>📄</span>;
    return <span style={{ marginRight: "6px" }}>📄</span>;
};

const FolderIcon = ({ open }: { open: boolean }) => (
    <span style={{ marginRight: "6px", color: "#dcb67a" }}>{open ? "📂" : "📁"}</span>
);

type ContextMenuState = {
    x: number;
    y: number;
    path: string | null; // null = root
    kind: "file" | "folder" | "root";
};

export default function FileExplorer({ workspace, dispatch }: { workspace: WorkspaceState; dispatch: React.Dispatch<any> }) {
    const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(new Set());
    const [creatingIn, setCreatingIn] = useState<{ parentPath: string; kind: "file" | "folder" } | null>(null);
    const [newItemName, setNewItemName] = useState("");
    const [renamingPath, setRenamingPath] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState("");
    const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
    const explorerRef = useRef<HTMLDivElement>(null);

    const tree = useMemo(() => buildTree(workspace.files), [workspace.files]);

    // Close context menu on click outside
    useEffect(() => {
        const handleClick = () => setContextMenu(null);
        document.addEventListener("click", handleClick);
        return () => document.removeEventListener("click", handleClick);
    }, []);

    const toggleCollapse = (path: string) => {
        const newSet = new Set(collapsedPaths);
        if (newSet.has(path)) newSet.delete(path);
        else newSet.add(path);
        setCollapsedPaths(newSet);
    };

    const handleCreate = () => {
        if (!newItemName || !creatingIn) {
            setCreatingIn(null);
            return;
        }
        
        let path = creatingIn.parentPath ? `${creatingIn.parentPath}/${newItemName}` : newItemName;
        
        if (creatingIn.kind === "folder") {
            // Create implicit folder by creating .keep file
            path = `${path}/.keep`;
            dispatch({ type: "FILE_CREATE", payload: { path, content: "" } });
        } else {
            dispatch({ type: "FILE_CREATE", payload: { path, content: "" } });
        }
        
        setCreatingIn(null);
        setNewItemName("");
    };

    const handleRename = () => {
        if (!renamingPath || !renameValue || renameValue === renamingPath) {
            setRenamingPath(null);
            setRenameValue("");
            return;
        }
        
        if (workspace.files[renamingPath] !== undefined) {
            // File
            const parentDir = renamingPath.substring(0, renamingPath.lastIndexOf("/"));
            const newPath = parentDir ? `${parentDir}/${renameValue}` : renameValue;
            dispatch({ type: "FILE_RENAME", payload: { oldPath: renamingPath, newPath } });
        } else {
            // Folder
            const parentDir = renamingPath.substring(0, renamingPath.lastIndexOf("/"));
            const newPrefix = parentDir ? `${parentDir}/${renameValue}` : renameValue;
            dispatch({ type: "FOLDER_RENAME", payload: { oldPrefix: renamingPath, newPrefix } });
        }
        
        setRenamingPath(null);
        setRenameValue("");
    };

    const handleDelete = (path: string, kind: "file" | "folder") => {
        if (!confirm(`Delete ${kind} "${path}"?`)) return;
        if (kind === "file") {
            dispatch({ type: "FILE_DELETE", payload: { path } });
        } else {
            dispatch({ type: "FOLDER_DELETE", payload: { prefix: path } });
        }
    };

    const handleContextMenu = (e: React.MouseEvent, path: string | null, kind: "file" | "folder" | "root") => {
        e.preventDefault();
        e.stopPropagation();
        setContextMenu({ x: e.clientX, y: e.clientY, path, kind });
    };

    const renderNode = (node: TreeNode, depth: number) => {
        const isOpen = !collapsedPaths.has(node.path);
        const isRenaming = renamingPath === node.path;
        const isEntrypoint = workspace.entrypoint === node.path;
        const isActive = workspace.activeFile === node.path;
        
        if (node.name === ".keep") return null;

        return (
            <div key={node.path || "root"}>
                {node.path && (
                    <div 
                        style={{ 
                            paddingLeft: `${depth * 12 + 8}px`,
                            paddingRight: "8px",
                            paddingTop: "2px",
                            paddingBottom: "2px",
                            cursor: "pointer",
                            background: isActive ? "#37373d" : (contextMenu?.path === node.path ? "#2a2d2e" : "transparent"),
                            color: isActive ? "#fff" : "#ccc",
                            display: "flex",
                            alignItems: "center",
                            fontSize: "0.9rem",
                            userSelect: "none",
                            border: contextMenu?.path === node.path ? "1px solid #007acc" : "1px solid transparent"
                        }}
                        onClick={() => {
                            if (node.kind === "folder") toggleCollapse(node.path);
                            else dispatch({ type: "FILE_OPEN", payload: { path: node.path } });
                        }}
                        onContextMenu={(e) => handleContextMenu(e, node.path, node.kind)}
                        className="fileItem"
                    >
                        {node.kind === "folder" && (
                            <span 
                                onClick={(e) => { e.stopPropagation(); toggleCollapse(node.path); }}
                                style={{ width: "16px", display: "inline-block", textAlign: "center", opacity: 0.7 }}
                            >
                                {isOpen ? "▼" : "▶"}
                            </span>
                        )}
                        {node.kind === "folder" ? <FolderIcon open={isOpen} /> : <FileIcon name={node.name} />}
                        
                        {isRenaming ? (
                            <input 
                                autoFocus
                                value={renameValue}
                                onChange={e => setRenameValue(e.target.value)}
                                onKeyDown={e => e.key === "Enter" && handleRename()}
                                onBlur={handleRename}
                                onClick={e => e.stopPropagation()}
                                style={{ background: "#333", color: "#fff", border: "1px solid #007acc", padding: "0 2px", flex: 1 }}
                            />
                        ) : (
                            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{node.name}</span>
                        )}

                        {isEntrypoint && <span style={{ fontSize: "0.8rem", color: "gold", marginLeft: "4px" }} title="Entrypoint">★</span>}
                    </div>
                )}

                {/* Children */}
                {node.kind === "folder" && isOpen && node.children && (
                    <div>
                        {/* Creation Input */}
                        {creatingIn && creatingIn.parentPath === node.path && (
                            <div style={{ paddingLeft: `${(depth + 1) * 12 + 24}px`, paddingRight: "8px", display: "flex", alignItems: "center" }}>
                                <span style={{ marginRight: "6px" }}>{creatingIn.kind === "folder" ? "📁" : "📄"}</span>
                                <input 
                                    autoFocus
                                    value={newItemName}
                                    onChange={e => setNewItemName(e.target.value)}
                                    onKeyDown={e => e.key === "Enter" && handleCreate()}
                                    onBlur={() => { if (!newItemName) setCreatingIn(null); else handleCreate(); }}
                                    placeholder={creatingIn.kind === "folder" ? "Folder Name" : "filename.py"}
                                    style={{ background: "#333", color: "#fff", border: "1px solid #007acc", width: "100%" }}
                                />
                            </div>
                        )}
                        {/* Sort: Folders first, then files */}
                        {Object.values(node.children)
                            .sort((a, b) => {
                                if (a.kind === b.kind) return a.name.localeCompare(b.name);
                                return a.kind === "folder" ? -1 : 1;
                            })
                            .map(child => renderNode(child, depth + 1))
                        }
                    </div>
                )}
            </div>
        );
    };

    return (
        <div 
            className="fileExplorer" 
            style={{ width: "220px", background: "#1e1e1e", borderRight: "1px solid #333", display: "flex", flexDirection: "column", height: "100%" }}
            onContextMenu={(e) => handleContextMenu(e, null, "root")}
        >
            <style>{`
                .fileItem:hover { background: #2a2d2e !important; }
            `}</style>
            
            <div style={{ padding: "8px", borderBottom: "1px solid #333", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: "bold", fontSize: "0.8rem", color: "#ccc", textTransform: "uppercase" }}>Explorer</span>
            </div>

            <div style={{ flex: 1, overflowY: "auto", paddingTop: "4px" }} ref={explorerRef}>
                {creatingIn && creatingIn.parentPath === "" && (
                    <div style={{ paddingLeft: "12px", paddingRight: "8px", display: "flex", alignItems: "center", marginBottom: "4px" }}>
                        <span style={{ marginRight: "6px" }}>{creatingIn.kind === "folder" ? "📁" : "📄"}</span>
                        <input 
                            autoFocus
                            value={newItemName}
                            onChange={e => setNewItemName(e.target.value)}
                            onKeyDown={e => e.key === "Enter" && handleCreate()}
                            onBlur={() => { if (!newItemName) setCreatingIn(null); else handleCreate(); }}
                            placeholder={creatingIn.kind === "folder" ? "Folder Name" : "filename.py"}
                            style={{ background: "#333", color: "#fff", border: "1px solid #007acc", width: "100%" }}
                        />
                    </div>
                )}
                
                {Object.values(tree.children || {})
                    .sort((a, b) => {
                        if (a.kind === b.kind) return a.name.localeCompare(b.name);
                        return a.kind === "folder" ? -1 : 1;
                    })
                    .map(child => renderNode(child, 0))
                }
                
                {/* Empty state or spacer to ensure right click works on empty space */}
                <div style={{ flex: 1, minHeight: "20px" }} />
            </div>
            
            <div style={{ padding: "8px", borderTop: "1px solid #333", fontSize: "0.75rem", color: "#666", background: "#1e1e1e" }}>
                <div style={{ marginBottom: "2px", display: "flex", justifyContent: "space-between" }}>
                    <span>ENTRY:</span>
                    <span style={{ color: "#ccc" }} title={workspace.entrypoint}>{workspace.entrypoint.split("/").pop()}</span>
                </div>
                <div style={{ color: "#888", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    $ python {workspace.entrypoint}
                </div>
            </div>

            {/* Context Menu */}
            {contextMenu && (
                <div 
                    style={{ 
                        position: "fixed", 
                        top: contextMenu.y, 
                        left: contextMenu.x, 
                        background: "#252526", 
                        border: "1px solid #454545", 
                        boxShadow: "0 2px 8px rgba(0,0,0,0.5)",
                        zIndex: 1000,
                        minWidth: "150px",
                        borderRadius: "4px",
                        padding: "4px 0"
                    }}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div 
                        className="ctxItem" 
                        onClick={() => { 
                            setCreatingIn({ parentPath: contextMenu.path || "", kind: "file" }); 
                            if (contextMenu.path) setCollapsedPaths(prev => { const n = new Set(prev); n.delete(contextMenu.path!); return n; });
                            setContextMenu(null); 
                        }}
                        style={{ padding: "4px 12px", cursor: "pointer", color: "#ccc", fontSize: "0.9rem" }}
                    >
                        New File
                    </div>
                    <div 
                        className="ctxItem" 
                        onClick={() => { 
                            setCreatingIn({ parentPath: contextMenu.path || "", kind: "folder" }); 
                            if (contextMenu.path) setCollapsedPaths(prev => { const n = new Set(prev); n.delete(contextMenu.path!); return n; });
                            setContextMenu(null); 
                        }}
                        style={{ padding: "4px 12px", cursor: "pointer", color: "#ccc", fontSize: "0.9rem" }}
                    >
                        New Folder
                    </div>
                    
                    {contextMenu.kind !== "root" && <div style={{ height: "1px", background: "#454545", margin: "4px 0" }} />}
                    
                    {contextMenu.kind !== "root" && (
                        <div 
                            className="ctxItem" 
                            onClick={() => { 
                                setRenamingPath(contextMenu.path); 
                                setRenameValue(contextMenu.path!.split("/").pop()!); 
                                setContextMenu(null); 
                            }}
                            style={{ padding: "4px 12px", cursor: "pointer", color: "#ccc", fontSize: "0.9rem" }}
                        >
                            Rename
                        </div>
                    )}
                    
                    {contextMenu.kind !== "root" && (
                        <div 
                            className="ctxItem" 
                            onClick={() => { 
                                handleDelete(contextMenu.path!, contextMenu.kind as "file" | "folder"); 
                                setContextMenu(null); 
                            }}
                            style={{ padding: "4px 12px", cursor: "pointer", color: "#d7ba7d", fontSize: "0.9rem" }}
                        >
                            Delete
                        </div>
                    )}

                    {contextMenu.kind === "file" && workspace.entrypoint !== contextMenu.path && (
                        <>
                            <div style={{ height: "1px", background: "#454545", margin: "4px 0" }} />
                            <div 
                                className="ctxItem" 
                                onClick={() => { 
                                    dispatch({ type: "SET_ENTRYPOINT", payload: { path: contextMenu.path! } });
                                    setContextMenu(null); 
                                }}
                                style={{ padding: "4px 12px", cursor: "pointer", color: "gold", fontSize: "0.9rem" }}
                            >
                                Set as Entrypoint
                            </div>
                        </>
                    )}
                    <style>{`.ctxItem:hover { background: #094771; color: #fff; }`}</style>
                </div>
            )}
        </div>
    );
}
