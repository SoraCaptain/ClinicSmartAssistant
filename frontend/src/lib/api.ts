// Typed client for the backend API (DESIGN §6). Split-origin dev falls back to
// localhost:8000; the k8s image build inlines the ingress origin via
// NEXT_PUBLIC_API_URL (it is a build-time constant in the client bundle).
import type { BookingJoined, ChatResponse, PatientContext, SummaryResult } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Demo identity (DESIGN §1: fixed patient P001, John Doe). */
export const PATIENT_ID = "P001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = init ? await fetch(`${API_BASE}${path}`, init) : await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = `HTTP ${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body?.detail !== undefined) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // non-JSON error body: keep the status text
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function postChat(sessionId: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }), // patient_id: backend default P001
  });
}

export function getBookings(patientId: string = PATIENT_ID): Promise<BookingJoined[]> {
  return request<BookingJoined[]>(`/api/bookings?patient_id=${encodeURIComponent(patientId)}`);
}

export function getPatientContext(patientId: string = PATIENT_ID): Promise<PatientContext> {
  return request<PatientContext>(`/api/patients/${encodeURIComponent(patientId)}/context`);
}

export function postSummarize(transcript: string): Promise<SummaryResult> {
  return request<SummaryResult>("/api/summarize/transcript", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
}
