
export interface WorkspaceState {
    files: Record<string, string>;
    openFiles: string[];
    activeFile: string | null;
    entrypoint: string;
}

export type WorkspaceAction =
    | { type: "FILE_CREATE"; payload: { path: string; content?: string } }
    | { type: "FILE_UPDATE"; payload: { path: string; content: string } }
    | { type: "FILE_DELETE"; payload: { path: string } }
    | { type: "FILE_RENAME"; payload: { oldPath: string; newPath: string } }
    | { type: "FOLDER_DELETE"; payload: { prefix: string } }
    | { type: "FOLDER_RENAME"; payload: { oldPrefix: string; newPrefix: string } }
    | { type: "FILE_OPEN"; payload: { path: string } }
    | { type: "FILE_CLOSE"; payload: { path: string } }
    | { type: "FILE_SET_ACTIVE"; payload: { path: string } }
    | { type: "SET_ENTRYPOINT"; payload: { path: string } }
    | { type: "INIT_WORKSPACE"; payload: { files: Record<string, string>; entrypoint: string } };

export const initialWorkspaceState: WorkspaceState = {
    files: { "main.py": "" },
    openFiles: ["main.py"],
    activeFile: "main.py",
    entrypoint: "main.py"
};

export function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
    switch (action.type) {
        case "FILE_CREATE":
            if (state.files[action.payload.path]) return state;
            return {
                ...state,
                files: { ...state.files, [action.payload.path]: action.payload.content || "" },
                openFiles: [...state.openFiles, action.payload.path],
                activeFile: action.payload.path
            };
        case "FILE_UPDATE":
            return {
                ...state,
                files: { ...state.files, [action.payload.path]: action.payload.content }
            };
        case "FILE_DELETE": {
            const newFiles = { ...state.files };
            delete newFiles[action.payload.path];
            const newOpen = state.openFiles.filter(p => p !== action.payload.path);
            let newActive = state.activeFile;
            if (state.activeFile === action.payload.path) {
                newActive = newOpen.length > 0 ? newOpen[newOpen.length - 1] : null;
            }
            return {
                ...state,
                files: newFiles,
                openFiles: newOpen,
                activeFile: newActive
            };
        }
        case "FILE_RENAME": {
            const content = state.files[action.payload.oldPath];
            if (content === undefined) return state;
            const newFiles = { ...state.files };
            delete newFiles[action.payload.oldPath];
            newFiles[action.payload.newPath] = content;
            
            const newOpen = state.openFiles.map(p => p === action.payload.oldPath ? action.payload.newPath : p);
            const newActive = state.activeFile === action.payload.oldPath ? action.payload.newPath : state.activeFile;
            const newEntry = state.entrypoint === action.payload.oldPath ? action.payload.newPath : state.entrypoint;
            
            return {
                ...state,
                files: newFiles,
                openFiles: newOpen,
                activeFile: newActive,
                entrypoint: newEntry
            };
        }
        case "FOLDER_DELETE": {
            const prefix = action.payload.prefix;
            // Ensure prefix ends with /
            const safePrefix = prefix.endsWith("/") ? prefix : prefix + "/";
            
            const newFiles = { ...state.files };
            let hasChanges = false;
            
            Object.keys(state.files).forEach(path => {
                if (path.startsWith(safePrefix)) {
                    delete newFiles[path];
                    hasChanges = true;
                }
            });
            
            if (!hasChanges) return state;
            
            const newOpen = state.openFiles.filter(p => !p.startsWith(safePrefix));
            let newActive = state.activeFile;
            if (state.activeFile && state.activeFile.startsWith(safePrefix)) {
                newActive = newOpen.length > 0 ? newOpen[newOpen.length - 1] : null;
            }
            // If entrypoint deleted, reset to main.py? Or leave dangling?
            // Better keep it, user can fix.
            
            return {
                ...state,
                files: newFiles,
                openFiles: newOpen,
                activeFile: newActive
            };
        }
        case "FOLDER_RENAME": {
            const oldPrefix = action.payload.oldPrefix.endsWith("/") ? action.payload.oldPrefix : action.payload.oldPrefix + "/";
            const newPrefix = action.payload.newPrefix.endsWith("/") ? action.payload.newPrefix : action.payload.newPrefix + "/";
            
            const newFiles = { ...state.files };
            let hasChanges = false;
            
            // Map for updating open files / entrypoint
            const renames: Record<string, string> = {};
            
            Object.keys(state.files).forEach(path => {
                if (path.startsWith(oldPrefix)) {
                    const suffix = path.slice(oldPrefix.length);
                    const newPath = newPrefix + suffix;
                    newFiles[newPath] = state.files[path];
                    delete newFiles[path];
                    renames[path] = newPath;
                    hasChanges = true;
                }
            });
            
            if (!hasChanges) return state;
            
            const newOpen = state.openFiles.map(p => renames[p] || p);
            const newActive = state.activeFile && renames[state.activeFile] ? renames[state.activeFile] : state.activeFile;
            const newEntry = renames[state.entrypoint] || state.entrypoint;
            
            return {
                ...state,
                files: newFiles,
                openFiles: newOpen,
                activeFile: newActive,
                entrypoint: newEntry
            };
        }
        case "FILE_OPEN":
            if (!state.openFiles.includes(action.payload.path)) {
                return {
                    ...state,
                    openFiles: [...state.openFiles, action.payload.path],
                    activeFile: action.payload.path
                };
            }
            return { ...state, activeFile: action.payload.path };
        case "FILE_CLOSE": {
            const newOpen = state.openFiles.filter(p => p !== action.payload.path);
            let newActive = state.activeFile;
            if (state.activeFile === action.payload.path) {
                newActive = newOpen.length > 0 ? newOpen[newOpen.length - 1] : null;
            }
            return { ...state, openFiles: newOpen, activeFile: newActive };
        }
        case "FILE_SET_ACTIVE":
            return { ...state, activeFile: action.payload.path };
        case "SET_ENTRYPOINT":
            return { ...state, entrypoint: action.payload.path };
        case "INIT_WORKSPACE":
            return {
                files: action.payload.files,
                openFiles: Object.keys(action.payload.files),
                activeFile: action.payload.entrypoint,
                entrypoint: action.payload.entrypoint
            };
        default:
            return state;
    }
}
