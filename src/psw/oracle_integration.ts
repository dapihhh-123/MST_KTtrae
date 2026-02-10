export const ORACLE_AS_RUN_TESTS =
  String((import.meta as any).env?.VITE_ORACLE_AS_RUN_TESTS || "false").toLowerCase() === "true";

export const ORACLE_VERSION_STORAGE_KEY = "psw_oracle_version_id";

export function getOracleVersionIdForPSW(): string | null {
  try {
    return localStorage.getItem(ORACLE_VERSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setOracleVersionIdForPSW(versionId: string | null): void {
  try {
    if (!versionId) {
      localStorage.removeItem(ORACLE_VERSION_STORAGE_KEY);
      return;
    }
    localStorage.setItem(ORACLE_VERSION_STORAGE_KEY, versionId);
  } catch {
    // no-op in restricted environments
  }
}
