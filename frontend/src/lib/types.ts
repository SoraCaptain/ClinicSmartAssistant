// Wire types mirroring backend/app/schemas (DESIGN §6). Dates/times arrive as
// JSON strings ("2026-11-05", "10:30:00"); render with string slicing, no parsing.

export interface BookingOut {
  booking_id: string;
  patient_id: string;
  doctor_id: string;
  treatment_id: string;
  booking_date: string; // YYYY-MM-DD
  booking_time: string; // HH:MM[:SS]
  status: string;
  notes: string | null;
  created_at: string;
  source: string;
}

/** Joined read model from GET /api/bookings (P5). */
export interface BookingJoined extends BookingOut {
  doctor_name: string;
  doctor_specialty: string;
  treatment_name: string;
  clinic_id: string;
  clinic_name: string;
}

export interface PatientProfile {
  patient_id: string;
  first_name: string;
  last_name: string;
  dob: string;
  gender: string;
  phone: string;
  email: string;
  known_allergies: string; // comma-separated
  emergency_contact: string;
}

export interface HistoryRecord {
  record_id: string;
  patient_id: string;
  doctor_id: string;
  visit_date: string;
  chief_complaint: string;
  diagnosis: string;
  prescribed_medication: string;
  doctor_notes: string;
}

/** GET /api/patients/{id}/context (P8 payload). */
export interface PatientContext {
  profile: PatientProfile;
  treatment_history: HistoryRecord[];
  upcoming_bookings: BookingJoined[];
}

export interface ChatResponse {
  reply: string;
  intent: string; // qa | check_bookings | book_appointment | general (rendered, not enforced)
  booking_created: BookingOut | null;
  session_id: string;
}

/** One rendered chat entry (user text, assistant reply, or error bubble). */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  intent?: string;
  booking?: BookingOut; // confirmation card when a turn completed a booking
  isError?: boolean;
}
