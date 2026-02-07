import { useState } from "react";
import IDE from "./components/IDE";
import SessionSelector from "./components/SessionSelector";

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Note: We deliberately do NOT auto-load from localStorage here,
  // to satisfy the requirement "Every time I refresh... I can choose".
  
  if (sessionId) {
    return <IDE sessionId={sessionId} onExit={() => setSessionId(null)} />;
  }

  return <SessionSelector onSelect={setSessionId} />;
}
