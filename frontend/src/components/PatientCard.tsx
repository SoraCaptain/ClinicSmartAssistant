"use client";

import { useCallback, useEffect, useState } from "react";
import { getPatientContext, PATIENT_ID } from "@/lib/api";
import type { PatientContext } from "@/lib/types";

/** P001 profile + allergy badges from GET /api/patients/{id}/context (P8 payload). */
export default function PatientCard({
  patientId = PATIENT_ID,
  refreshKey = 0,
}: {
  patientId?: string;
  refreshKey?: number;
}) {
  const [ctx, setCtx] = useState<PatientContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCtx(await getPatientContext(patientId));
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
    <section className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Patient
      </h2>
      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 p-2 text-xs text-red-700">
          <p>{error}</p>
          <button type="button" onClick={() => void load()} className="mt-1 font-medium underline">
            Retry
          </button>
        </div>
      )}
      {loading && !ctx ? (
        <p className="py-6 text-center text-sm text-slate-400">Loading…</p>
      ) : ctx ? (
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-semibold">
              {ctx.profile.first_name} {ctx.profile.last_name}
              <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-normal text-slate-500">
                {ctx.profile.patient_id}
              </span>
            </p>
            <p className="text-xs text-slate-500">
              {ctx.profile.gender} · DOB {ctx.profile.dob}
            </p>
          </div>
          <dl className="space-y-1 text-xs text-slate-600">
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-slate-400">Phone</dt>
              <dd>{ctx.profile.phone}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-slate-400">Email</dt>
              <dd className="break-all">{ctx.profile.email}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-slate-400">Emergency</dt>
              <dd>{ctx.profile.emergency_contact}</dd>
            </div>
          </dl>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Allergies</p>
            <div className="flex flex-wrap gap-1">
              {Array.from(
                new Set(
                  ctx.profile.known_allergies
                    .split(",")
                    .map((a) => a.trim())
                    .filter(Boolean),
                ),
              ).map((a) => (
                  <span
                    key={a}
                    className="rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-medium text-red-700"
                  >
                    ⚠ {a}
                  </span>
                ))}
            </div>
          </div>
          {ctx.treatment_history.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-slate-500">Treatment history</p>
              <ul className="space-y-1 text-xs text-slate-600">
                {ctx.treatment_history.map((h) => (
                  <li key={h.record_id}>
                    <span className="text-slate-400">{h.visit_date}</span> — {h.chief_complaint}
                    <span className="text-slate-400"> → {h.diagnosis}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
