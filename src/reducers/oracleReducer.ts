import type { 
    OracleStage, ApiLogEntry, GenerateSpecResponse, GenerateTestsResponse, RunResponse, 
    OracleVersion, CreateTaskResponse, ConfirmResponse 
} from "../types/oracle";

export interface OracleState {
    stage: OracleStage;
    taskId?: string;
    currentVersionId?: string;
    versions: OracleVersion[];
    
    specResponse?: GenerateSpecResponse;
    ambiguitySelections: Record<string, string>;
    testsResponse?: GenerateTestsResponse;
    runHistory: Array<{ ts: number; versionId: string; codeHash?: string; run: RunResponse }>;
    apiLog: ApiLogEntry[];
    
    warning?: { type: "low_confidence" | "error"; message: string };
    loadingFlags: {
        createTask?: boolean;
        spec?: boolean;
        confirm?: boolean;
        tests?: boolean;
        run?: boolean;
    };
}

export type OracleAction =
    | { type: "TASK_CREATED"; payload: CreateTaskResponse }
    | { type: "TASK_LOADED"; payload: { taskId: string; versions: any[] } }
    | { type: "SPEC_GENERATED"; payload: GenerateSpecResponse }
    | { type: "AMBIGUITY_SELECT"; payload: { id: string; choiceId: string } }
    | { type: "CONFIRMED"; payload: ConfirmResponse }
    | { type: "TESTS_GENERATED"; payload: GenerateTestsResponse }
    | { type: "RUN_STARTED" }
    | { type: "RUN_DONE"; payload: RunResponse }
    | { type: "SET_LOADING"; payload: { key: keyof OracleState["loadingFlags"]; value: boolean } }
    | { type: "SET_WARNING"; payload: { type: "low_confidence" | "error"; message: string } | undefined }
    | { type: "SWITCH_VERSION"; payload: string }
    | { type: "VERSION_DETAILS_LOADED"; payload: any }
    | { type: "LOG_API"; payload: ApiLogEntry };

export const initialOracleState: OracleState = {
    stage: "init",
    versions: [],
    ambiguitySelections: {},
    runHistory: [],
    apiLog: [],
    loadingFlags: {}
};

export function oracleReducer(state: OracleState, action: OracleAction): OracleState {
    switch (action.type) {
        case "TASK_CREATED":
            return {
                ...state,
                taskId: action.payload.task_id,
                stage: "init",
                versions: []
            };

        case "TASK_LOADED": {
             // Reconstruct versions list
             const vers: OracleVersion[] = action.payload.versions.map((v: any) => ({
                 versionId: v.version_id,
                 createdAt: v.created_at * 1000,
                 status: v.status,
                 confidence: v.oracle_confidence,
                 hiddenTestsCount: v.hidden_tests_count
             }));
             // If we have versions, pick the last one
             const last = vers[vers.length - 1];
             let nextStage: OracleStage = "init";
             if (last) {
                 if (last.status === "awaiting_confirmation") nextStage = "awaiting_confirmation";
                 else if (last.hiddenTestsCount && last.hiddenTestsCount > 0) nextStage = "tests_generated";
                 else if (last.status === "ready") nextStage = "ready_no_tests";
             }
             return {
                 ...state,
                 taskId: action.payload.taskId,
                 versions: vers,
                 currentVersionId: last?.versionId,
                 stage: nextStage
             };
        }

        case "SPEC_GENERATED": {
            const { version_id, spec_summary, ambiguities, oracle_confidence_initial } = action.payload;
            
            // Add or update version in list
            const newVer: OracleVersion = {
                versionId: version_id,
                createdAt: Date.now(),
                status: ambiguities.length > 0 ? "awaiting_confirmation" : "ready",
                confidence: oracle_confidence_initial,
                specSummary: spec_summary
            };
            
            // Determine stage
            let nextStage: OracleStage = "ready_no_tests";
            if (ambiguities.length > 0) nextStage = "awaiting_confirmation";
            
            let warning = state.warning;
            if (oracle_confidence_initial < 0.4) {
                warning = { type: "low_confidence", message: "Initial confidence is low (<0.4)." };
            } else {
                warning = undefined;
            }

            return {
                ...state,
                currentVersionId: version_id,
                specResponse: action.payload,
                versions: [...state.versions, newVer],
                stage: nextStage,
                warning,
                ambiguitySelections: {} // reset selections for new version
            };
        }

        case "AMBIGUITY_SELECT":
            return {
                ...state,
                ambiguitySelections: {
                    ...state.ambiguitySelections,
                    [action.payload.id]: action.payload.choiceId
                }
            };

        case "CONFIRMED": {
            const { status } = action.payload;
            let nextStage: OracleStage = "ready_no_tests";
            if (status === "low_confidence") {
                // Keep it ready but maybe show warning?
                // The contract says status can be "low_confidence".
            }
            
            // Update version status in list
            const newVersions = state.versions.map(v => 
                v.versionId === action.payload.version_id ? { ...v, status } : v
            );

            return {
                ...state,
                stage: nextStage,
                versions: newVersions,
                warning: status === "low_confidence" ? { type: "low_confidence", message: "Confirmed but confidence remains low." } : undefined
            };
        }

        case "TESTS_GENERATED": {
            const { version_id, status, oracle_confidence, hidden_tests_count } = action.payload;
            
            // Update version
            const newVersions = state.versions.map(v => 
                v.versionId === version_id ? { ...v, status, confidence: oracle_confidence, hiddenTestsCount: hidden_tests_count } : v
            );

            return {
                ...state,
                testsResponse: action.payload,
                versions: newVersions,
                stage: "tests_generated",
                warning: oracle_confidence < 0.4 ? { type: "low_confidence", message: "Tests generated with low confidence." } : undefined
            };
        }

        case "RUN_STARTED":
            return { ...state, stage: "running" };

        case "RUN_DONE":
            return {
                ...state,
                stage: "run_done",
                runHistory: [{ ts: Date.now(), versionId: action.payload.version_id, run: action.payload }, ...state.runHistory]
            };

        case "SET_LOADING":
            return {
                ...state,
                loadingFlags: { ...state.loadingFlags, [action.payload.key]: action.payload.value }
            };

        case "SET_WARNING":
            return { ...state, warning: action.payload };

        case "SWITCH_VERSION":
            // Just switch ID. Data for that version (spec, tests) should be loaded via async calls (which will dispatch VERSION_DETAILS_LOADED)
            // But here we just set the ID.
            return { ...state, currentVersionId: action.payload };
        
        case "VERSION_DETAILS_LOADED": {
            // Populate specResponse, testsResponse from loaded data
            const d = action.payload;
            return {
                ...state,
                specResponse: {
                    version_id: state.currentVersionId!, // assumed
                    spec_summary: d.spec_summary,
                    ambiguities: d.ambiguities,
                    oracle_confidence_initial: d.oracle_confidence,
                    confidence_reasons: [],
                    log_id: ""
                },
                ambiguitySelections: d.confirmations?.selections || {},
                testsResponse: d.public_examples ? {
                    version_id: state.currentVersionId!,
                    status: d.status,
                    oracle_confidence: d.oracle_confidence,
                    confidence_reasons: [],
                    public_examples_preview: d.public_examples,
                    hidden_tests_count: d.hidden_tests_count,
                    hash: d.hash,
                    log_id: ""
                } : undefined,
                stage: d.hidden_tests_count > 0 ? "tests_generated" : (d.ambiguities?.length > 0 && Object.keys(d.confirmations || {}).length === 0 ? "awaiting_confirmation" : "ready_no_tests")
            };
        }

        case "LOG_API":
            return { ...state, apiLog: [action.payload, ...state.apiLog].slice(0, 100) }; // Keep last 100

        default:
            return state;
    }
}
