// Per-browser chat session id (DESIGN §8): minted once, persisted in localStorage,
// reused across turns so the LangGraph checkpointer keeps thread state.
const STORAGE_KEY = "clinicpilot-session-id";

// crypto.randomUUID needs a secure context (localhost/https) and a newer
// browser; getRandomValues works everywhere and yields the same v4 shape.
function uuidV4(): string {
  const c = window.crypto as Crypto & { randomUUID?: () => string };
  if (typeof c.randomUUID === "function") return c.randomUUID();
  const bytes = c.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getSessionId(): string {
  if (typeof window === "undefined") {
    throw new Error("getSessionId is browser-only");
  }
  let id = window.localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = uuidV4();
    window.localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

/** Make an existing session the active one (sidebar selection persists across reloads). */
export function setSessionId(id: string): void {
  if (typeof window === "undefined") {
    throw new Error("setSessionId is browser-only");
  }
  window.localStorage.setItem(STORAGE_KEY, id);
}

/** Start a new chat session: mint a fresh id, make it the active one, return it.
 * The old session's transcript stays in the backend (sidebar can reopen it). */
export function newSessionId(): string {
  if (typeof window === "undefined") {
    throw new Error("newSessionId is browser-only");
  }
  const id = uuidV4();
  window.localStorage.setItem(STORAGE_KEY, id);
  return id;
}
