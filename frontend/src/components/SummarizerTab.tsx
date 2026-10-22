"use client";

import { useState } from "react";
import { postSummarize } from "@/lib/api";
import type { SummaryResult } from "@/lib/types";

const FIELDS: { key: keyof SummaryResult; label: string }[] = [
  { key: "chief_complaint", label: "Chief complaint" },
  { key: "diagnosis", label: "Diagnosis" },
  { key: "medication", label: "Medication" },
  { key: "doctor_instructions", label: "Doctor instructions" },
];

const PLACEHOLDER =
  "Paste a doctor–patient transcript…\n\ne.g. Patient: My left knee has hurt for two weeks. Doctor: Any swelling? …";

// Bonus feature (DESIGN §8): transcript → four structured clinical fields.
export default function SummarizerTab() {
  const [transcript, setTranscript] = useState("");
  const [result, setResult] = useState<SummaryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function summarize(): Promise<void> {
    const text = transcript.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await postSummarize(text));
    } catch (err) {
      // P7-style errors surface verbatim — no canned fallback
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex h-[70vh] min-h-[480px] flex-col rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <textarea
        className="min-h-[120px] flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        placeholder={PLACEHOLDER}
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        aria-label="Transcript"
        disabled={busy}
      />
      <button
        type="button"
        onClick={() => void summarize()}
        className="mt-2 self-end rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={busy || transcript.trim().length === 0}
      >
        {busy ? "Summarizing…" : "Summarize"}
      </button>
      {error && (
        <div className="mt-2 rounded-md border border-red-300 bg-red-50 p-2 text-xs text-red-700">
          <p>{error}</p>
          <button type="button" onClick={() => void summarize()} className="mt-1 font-medium underline">
            Retry
          </button>
        </div>
      )}
      {result && (
        <dl className="mt-3 space-y-2 overflow-y-auto text-sm">
          {FIELDS.map(({ key, label }) => (
            <div key={key} className="rounded-md bg-slate-50 p-2 ring-1 ring-slate-200">
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
              <dd className="mt-0.5 text-slate-800">{result[key]}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
