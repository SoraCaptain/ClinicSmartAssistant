"use client";

import { useCallback, useEffect, useState } from "react";
import { getBookings, PATIENT_ID } from "@/lib/api";
import type { BookingJoined } from "@/lib/types";

// P5: refetch when refreshKey changes — the page bumps it after the chat
// creates a booking. No polling.
export default function BookingsPanel({
  patientId = PATIENT_ID,
  refreshKey = 0,
}: {
  patientId?: string;
  refreshKey?: number;
}) {
  const [rows, setRows] = useState<BookingJoined[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getBookings(patientId);
      setRows(
        [...data].sort(
          (a, b) =>
            a.booking_date.localeCompare(b.booking_date) || a.booking_time.localeCompare(b.booking_time),
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <section className="flex h-[70vh] min-h-[480px] flex-col rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          My bookings
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50"
        >
          ⟳ Refresh
        </button>
      </div>
      {error && (
        <div className="mb-2 rounded-md border border-red-300 bg-red-50 p-2 text-xs text-red-700">
          <p>{error}</p>
          <button type="button" onClick={() => void load()} className="mt-1 font-medium underline">
            Retry
          </button>
        </div>
      )}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <p className="py-6 text-center text-sm text-slate-400">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">No bookings yet.</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-1.5 pr-2 font-medium">Date</th>
                <th className="py-1.5 pr-2 font-medium">Time</th>
                <th className="py-1.5 pr-2 font-medium">Treatment</th>
                <th className="py-1.5 pr-2 font-medium">Doctor</th>
                <th className="py-1.5 pr-2 font-medium">Clinic</th>
                <th className="py-1.5 pr-2 font-medium">Status</th>
                <th className="py-1.5 font-medium">Ref</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.booking_id} className="border-b border-slate-100 align-top">
                  <td className="py-1.5 pr-2 whitespace-nowrap">{b.booking_date}</td>
                  <td className="py-1.5 pr-2 whitespace-nowrap">{b.booking_time.slice(0, 5)}</td>
                  <td className="py-1.5 pr-2">{b.treatment_name}</td>
                  <td className="py-1.5 pr-2">
                    {b.doctor_name}
                    <span className="block text-[10px] text-slate-400">{b.doctor_specialty}</span>
                  </td>
                  <td className="py-1.5 pr-2">{b.clinic_name}</td>
                  <td className="py-1.5 pr-2">
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                      {b.status}
                    </span>
                  </td>
                  <td className="py-1.5 font-mono text-[10px] text-slate-400">{b.booking_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="mt-2 text-[10px] text-slate-400">{rows.length} booking(s) · patient {patientId}</p>
    </section>
  );
}
