import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getSessionId, newSessionId, setSessionId } from "@/lib/session";

const STORAGE_KEY = "clinicpilot-session-id";

// jsdom/Node environments vary in crypto.randomUUID support; pin the exact
// environment where it is missing — the bug: "window.crypto.randomUUID is
// not a function" on non-secure origins / older browsers.
function withoutRandomUUID<T>(fn: () => T): T {
  const c = window.crypto as Crypto & { randomUUID?: () => string };
  const original = Object.getOwnPropertyDescriptor(c, "randomUUID");
  Object.defineProperty(c, "randomUUID", { value: undefined, configurable: true });
  try {
    return fn();
  } finally {
    if (original) Object.defineProperty(c, "randomUUID", original);
    else delete (c as { randomUUID?: () => string }).randomUUID;
  }
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

describe("getSessionId", () => {
  it("mints a uuid-v4-shaped id and persists it in localStorage", () => {
    const first = getSessionId();
    expect(first).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(localStorage.getItem(STORAGE_KEY)).toBe(first);

    expect(getSessionId()).toBe(first); // same session across turns
  });

  it("still mints a valid v4 id when crypto.randomUUID is missing", () => {
    const id = withoutRandomUUID(() => getSessionId());
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(localStorage.getItem(STORAGE_KEY)).toBe(id);
  });

  it("mints a fresh id after localStorage is cleared (new browser session)", () => {
    const first = getSessionId();
    localStorage.clear();
    const second = getSessionId();
    expect(second).not.toBe(first);
  });
});

describe("newSessionId", () => {
  it("mints a different id, makes it active, and keeps it stable across reads", () => {
    const before = getSessionId();
    const fresh = newSessionId();
    expect(fresh).not.toBe(before);
    expect(fresh).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(localStorage.getItem(STORAGE_KEY)).toBe(fresh);
    expect(getSessionId()).toBe(fresh); // the new session is the active one
  });
});

describe("setSessionId", () => {
  it("makes an existing session the active one across reads", () => {
    getSessionId(); // mint something else first
    setSessionId("s-old");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("s-old");
    expect(getSessionId()).toBe("s-old");
  });
});
