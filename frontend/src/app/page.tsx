"use client";

import { useCallback, useEffect, useState } from "react";
import BookingsPanel from "@/components/BookingsPanel";
import ChatPanel from "@/components/ChatPanel";
import PatientCard from "@/components/PatientCard";
import SessionSidebar from "@/components/SessionSidebar";
import SummarizerTab from "@/components/SummarizerTab";
import { getChatSessions } from "@/lib/api";
import { getSessionId, newSessionId, setSessionId } from "@/lib/session";
import type { ChatSessionSummary } from "@/lib/types";

// Single page (DESIGN §8): four panes; the P5 wire — chat bumps refreshKey on
// booking_created so bookings + patient card refetch without manual refresh.
// Multi-session chat: the page owns the active session id; the sidebar lists
// persisted sessions and switches the ChatPanel between them.
export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [rightTab, setRightTab] = useState<"bookings" | "summarizer">("bookings");
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await getChatSessions());
      setSessionsError(null);
    } catch (err) {
      setSessions([]);
      setSessionsError(err instanceof Error ? err.message : String(err)); // fail loud in the sidebar
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    setActiveSession(getSessionId()); // last active session survives reload
    void loadSessions();
  }, [loadSessions]);

  const selectSession = useCallback((id: string) => {
    setSessionId(id); // the selection is the active session across reloads
    setActiveSession(id);
  }, []);

  return (
    <main className="mx-auto max-w-[1600px] p-4 lg:p-6">
      <header className="mb-4 flex items-baseline justify-between">
        <h1 className="text-xl font-bold text-slate-800">ClinicPilot AI</h1>
        <p className="text-xs text-slate-500">demo patient P001 · John Doe</p>
      </header>
      <div className="grid gap-4 lg:grid-cols-[210px_260px_minmax(0,1fr)_380px]">
        <SessionSidebar
          sessions={sessions}
          activeId={activeSession}
          onSelect={selectSession}
          onNew={() => setActiveSession(newSessionId())}
          loading={sessionsLoading}
          error={sessionsError}
        />
        <div className="space-y-4">
          <PatientCard refreshKey={refreshKey} />
        </div>
        {activeSession && (
          <ChatPanel
            key={activeSession}
            sessionId={activeSession}
            onTurnDone={() => void loadSessions()}
            onBookingCreated={() => setRefreshKey((k) => k + 1)}
          />
        )}
        <div className="flex flex-col">
          <div className="mb-2 flex gap-1" role="tablist" aria-label="Right pane tabs">
            {(["bookings", "summarizer"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={rightTab === tab}
                onClick={() => setRightTab(tab)}
                className={
                  "rounded-md px-3 py-1 text-xs font-semibold uppercase tracking-wide " +
                  (rightTab === tab
                    ? "bg-blue-600 text-white"
                    : "bg-white text-slate-500 ring-1 ring-slate-200 hover:text-slate-700")
                }
              >
                {tab === "bookings" ? "My bookings" : "Summarizer"}
              </button>
            ))}
          </div>
          {rightTab === "bookings" ? (
            <BookingsPanel refreshKey={refreshKey} bare />
          ) : (
            <SummarizerTab />
          )}
        </div>
      </div>
    </main>
  );
}
