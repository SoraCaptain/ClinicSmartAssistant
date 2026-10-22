"use client";

import { useState } from "react";
import BookingsPanel from "@/components/BookingsPanel";
import ChatPanel from "@/components/ChatPanel";
import PatientCard from "@/components/PatientCard";
import SummarizerTab from "@/components/SummarizerTab";

// Single page (DESIGN §8): three panes; the P5 wire — chat bumps refreshKey on
// booking_created so bookings + patient card refetch without manual refresh.
// The right pane is tabbed: bookings (default) + the bonus transcript summarizer.
export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [rightTab, setRightTab] = useState<"bookings" | "summarizer">("bookings");

  return (
    <main className="mx-auto max-w-7xl p-4 lg:p-6">
      <header className="mb-4 flex items-baseline justify-between">
        <h1 className="text-xl font-bold text-slate-800">ClinicPilot AI</h1>
        <p className="text-xs text-slate-500">demo patient P001 · John Doe</p>
      </header>
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_380px]">
        <div className="space-y-4">
          <PatientCard refreshKey={refreshKey} />
        </div>
        <ChatPanel onBookingCreated={() => setRefreshKey((k) => k + 1)} />
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
