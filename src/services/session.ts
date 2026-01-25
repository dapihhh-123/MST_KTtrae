
export const STORAGE_KEY_SESSION = "kt_session_id";
export const STORAGE_KEY_WORKSPACE = "kt_workspace_id";

const API_BASE = (() => {
  const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined;
  if (envBase && typeof envBase === "string" && envBase.length > 0) return envBase;
  const host = typeof window !== "undefined" ? window.location.hostname : "";
  if (host && host !== "localhost" && host !== "127.0.0.1") return "http://127.0.0.1:8000/api";
  return "/api";
})();

function apiUrl(path: string): string {
  const base = API_BASE.endsWith("/") ? API_BASE.slice(0, -1) : API_BASE;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

export function getSessionId(): string | null {
  const current = localStorage.getItem(STORAGE_KEY_SESSION);
  if (current) return current;
  return null;
}

export function resetSessionLocal() {
  localStorage.removeItem(STORAGE_KEY_SESSION);
  // Optional: Reset workspace if needed, but usually we keep the workspace
  // localStorage.removeItem(STORAGE_KEY_WORKSPACE); 
}

export async function initSession(): Promise<string> {
  // 1. Try GET /api/session/default (Compliance 2.7-B)
  try {
      const res = await fetch(apiUrl("/session/default"));
      if (res.ok) {
          const data = await res.json();
          // data = { session_id, general_thread_id }
          if (data.session_id) {
              localStorage.setItem(STORAGE_KEY_SESSION, data.session_id);
              console.log("Session loaded:", data.session_id);
              return data.session_id;
          }
      }
  } catch (e) {
      console.warn("Failed to fetch default session", e);
  }

  // Fallback (legacy creation logic)
  let sessionId = getSessionId();
  let workspaceId = localStorage.getItem(STORAGE_KEY_WORKSPACE);
  if (!workspaceId) {
    // Try to list workspaces first to avoid cluttering if one exists (optional)
    try {
        const listRes = await fetch(apiUrl("/workspaces"));
        if (listRes.ok) {
            const list = await listRes.json();
            if (list.length > 0) {
                workspaceId = list[0].id;
            }
        }
    } catch (e) { console.warn(e); }

    if (!workspaceId) {
        const wsRes = await fetch(apiUrl("/workspaces"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: "Default Workspace" })
        });
        if (!wsRes.ok) {
          const text = await wsRes.text().catch(() => "");
          throw new Error(`Failed to create workspace: ${wsRes.status} ${wsRes.statusText}${text ? ` - ${text}` : ""}`);
        }
        const wsData = await wsRes.json();
        workspaceId = wsData.id;
    }
    localStorage.setItem(STORAGE_KEY_WORKSPACE, workspaceId!);
  }

  // 2. Create Session
  const sessRes = await fetch(apiUrl("/sessions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId, title: "Auto Session" })
  });
  
  if (!sessRes.ok) {
      const text = await sessRes.text().catch(() => "");
      throw new Error(`Failed to create session: ${sessRes.status} ${sessRes.statusText}${text ? ` - ${text}` : ""}`);
  }

  const sessData = await sessRes.json();
  sessionId = sessData.id;
  localStorage.setItem(STORAGE_KEY_SESSION, sessionId!);
  
  console.log("Session initialized:", sessionId);
  return sessionId!;
}
