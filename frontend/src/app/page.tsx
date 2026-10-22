"use client";

import { useState } from "react";
import BookingsPanel from "@/components/BookingsPanel";
import ChatPanel from "@/components/ChatPanel";
import PatientCard from "@/components/PatientCard";

// Single page (DESIGN §8): three panes; the P5 wire — chat bumps refreshKey on
// booking_created so bookings + patient card refetch without manual refresh.
export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);

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
        <BookingsPanel refreshKey={refreshKey} />
      </div>
    </main>
  );
}
