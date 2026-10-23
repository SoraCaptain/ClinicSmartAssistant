"use client";

import type { ChatSessionSummary } from "@/lib/types";

// Multi-session chat (DESIGN §8): leftmost column — start a new session or reopen
// a past one (its transcript loads into ChatPanel; chatting continues that thread).

function shortWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  loading = false,
  error = null,
}: {
  sessions: ChatSessionSummary[];
  activeId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <section
      className="flex flex-col gap-2 rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200 lg:h-[70vh]"
      aria-label="Chat sessions"
    >
      <button
        type="button"
        onClick={onNew}
        className="w-full shrink-0 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        + New session
      </button>
      {error ? (
        <p className="px-1 py-2 text-xs text-red-600">Couldn't load sessions: {error}</p>
      ) : loading && sessions.length === 0 ? (
        <p className="px-1 py-2 text-xs text-slate-400">Loading sessions…</p>
      ) : sessions.length === 0 ? (
        <p className="px-1 py-2 text-xs text-slate-400">
          No past sessions yet — your conversations will appear here.
        </p>
      ) : (
        <ul className="flex min-w-full gap-2 overflow-x-auto lg:min-w-0 lg:flex-1 lg:flex-col lg:overflow-x-visible lg:overflow-y-auto">
          {sessions.map((s) => {
            const active = s.session_id === activeId;
            return (
              <li key={s.session_id} className="shrink-0 lg:shrink">
                <button
                  type="button"
                  onClick={() => onSelect(s.session_id)}
                  aria-current={active ? "true" : undefined}
                  className={
                    "w-full rounded-lg px-3 py-2 text-left text-sm ring-1 lg:w-full " +
                    (active
                      ? "bg-blue-50 ring-blue-300"
                      : "bg-slate-50 ring-slate-200 hover:bg-slate-100")
                  }
                >
                  <span className="block truncate font-medium text-slate-800" title={s.title}>
                    {s.title}
                  </span>
                  <span className="block text-[10px] text-slate-400">{shortWhen(s.updated_at)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
