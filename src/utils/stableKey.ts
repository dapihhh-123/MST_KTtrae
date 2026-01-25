export function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32bit integer
  }
  return "h" + hash.toString(16);
}

export function makeMessageKey(scope: string, threadId: string, message: any): string {
  // 1. Server ID (backend generated)
  // Check both 'id' (standard) and 'message_id' (streaming payload sometimes uses this)
  if (message.id && !message.id.startsWith("msg_") && !message.id.startsWith("temp_")) {
    return `${scope}:${threadId}:${message.id}`;
  }
  
  // 2. Client ID (optimistic)
  if (message.client_id) {
    return `${scope}:${threadId}:${message.client_id}`;
  }

  // 3. Fallback for temp/local messages without client_id
  const role = message.role || "unknown";
  const created = message.createdAt || 0;
  const text = (message.content || "").slice(0, 32);
  const hash = simpleHash(`${role}:${created}:${text}`);
  
  // If message has a temp id, append it to reduce collision risk
  const tempId = message.id || "";
  
  return `${scope}:${threadId}:fallback:${hash}:${tempId}`;
}

export function makeChunkKey(scope: string, threadId: string, messageId: string, seq: number): string {
  return `${scope}:${threadId}:${messageId}:chunk:${seq}`;
}

export function makeHighlightKey(scope: string, threadId: string, messageId: string, index: number): string {
  return `${scope}:${threadId}:${messageId}:hl:${index}`;
}
