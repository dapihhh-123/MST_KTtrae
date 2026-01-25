import type { AgentResponse, ClientEvent, AgentAction } from "./actions";
import { uid, now, sleep } from "./utils";

export async function callAgent(event: ClientEvent): Promise<AgentResponse> {
  // Simulate network delay
  await sleep(600);

  const actions: AgentAction[] = [];

  if (event.type === "RUN") {
    actions.push(
      { type: "AI_SET_PRESENCE", presence: { loading: true, bubble: { emoji: "🚀", text: "Running code..." } } },
      { type: "CONSOLE_CLEAR" },
      { type: "WAIT", ms: 500 },
      { 
        type: "CONSOLE_APPEND", 
        entries: [{ id: uid("log"), kind: "stdout", text: "Running tests..." }] 
      },
      { type: "WAIT", ms: 300 },
      { 
        type: "CONSOLE_APPEND", 
        entries: [
          { id: uid("log"), kind: "stdout", text: "test_times_overlap ... PASS" },
          { id: uid("log"), kind: "info", text: "All tests passed (mock)." }
        ] 
      },
      { type: "AI_SET_PRESENCE", presence: { loading: false, bubble: null } }
    );
  } else if (event.type === "GLOBAL_MESSAGE") {
    actions.push(
      { type: "AI_SET_PRESENCE", presence: { loading: true, bubble: { emoji: "🤔", text: "Thinking..." } } },
      { type: "WAIT", ms: 800 },
      { type: "AI_SET_PRESENCE", presence: { loading: false, bubble: null } },
      { 
        type: "THREAD_APPEND_MESSAGE", 
        threadId: event.threadId, 
        message: { id: uid("msg"), role: "assistant", content: `I received your global message: "${event.text}". How can I help with the code?`, createdAt: now() } 
      }
    );
  } else if (event.type === "BREAKOUT_MESSAGE") {
    actions.push(
      { type: "AI_SET_PRESENCE", presence: { loading: true, bubble: { emoji: "👀", text: "Analyzing context..." } } },
      { type: "WAIT", ms: 800 },
      { type: "AI_SET_PRESENCE", presence: { loading: false, bubble: null } },
      { 
        type: "BREAKOUT_APPEND_MESSAGE", 
        breakoutId: event.breakoutId, 
        message: { id: uid("msg"), role: "assistant", content: `I see your question about this block: "${event.text}".`, createdAt: now() } 
      }
    );
  }

  return {
    requestId: uid("req"),
    actions
  };
}
