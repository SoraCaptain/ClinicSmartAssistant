import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BookingsPanel from "@/components/BookingsPanel";
import ChatPanel from "@/components/ChatPanel";
import type { BookingJoined, ChatResponse } from "@/lib/types";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function joinedBooking(overrides: Partial<BookingJoined> = {}): BookingJoined {
  return {
    booking_id: "B1001",
    patient_id: "P001",
    doctor_id: "D101",
    treatment_id: "T001",
    booking_date: "2026-11-05",
    booking_time: "10:30:00",
    status: "Confirmed",
    notes: null,
    created_at: "2026-10-01T09:00:00Z",
    source: "seed",
    doctor_name: "Dr. Alice Smith",
    doctor_specialty: "General Practice",
    treatment_name: "General Checkup",
    clinic_id: "C001",
    clinic_name: "City Health Clinic",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BookingsPanel", () => {
  it("renders the joined read model (treatment/doctor/clinic names, P5)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(200, [joinedBooking(), joinedBooking({ booking_id: "B1004", treatment_name: "Joint & Pain Consultation", booking_date: "2026-11-15" })])),
    );

    render(<BookingsPanel />);

    await waitFor(() => expect(screen.getByText("General Checkup")).toBeTruthy());
    expect(screen.getAllByText("Dr. Alice Smith").length).toBe(2); // both rows
    expect(screen.getAllByText("City Health Clinic").length).toBe(2);
    expect(screen.getByText("B1004")).toBeTruthy();
    expect(screen.getByText(/2 booking/)).toBeTruthy();
  });

  it("shows the backend error verbatim with a retry (fail loud)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, { detail: "AI service unavailable" })));

    render(<BookingsPanel />);

    await waitFor(() => expect(screen.getByText("AI service unavailable")).toBeTruthy());
  });
});

describe("ChatPanel", () => {
  function chatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
    return {
      reply: "You're booked! General Checkup on 2026-11-20 at 14:00.",
      intent: "book_appointment",
      booking_created: {
        booking_id: "B-ab12cd",
        patient_id: "P001",
        doctor_id: "D101",
        treatment_id: "T001",
        booking_date: "2026-11-20",
        booking_time: "14:00:00",
        status: "Confirmed",
        notes: null,
        created_at: "2026-10-22T10:00:00Z",
        source: "chatbot",
      },
      session_id: "s1",
      ...overrides,
    };
  }

  async function send(message: string) {
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: message } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  }

  it("renders reply + confirmation card and fires onBookingCreated exactly once when a booking is created", async () => {
    const onBookingCreated = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, chatResponse())));

    render(<ChatPanel onBookingCreated={onBookingCreated} />);
    await send("Book a general checkup");

    await waitFor(() => expect(screen.getByText(/You're booked!/)).toBeTruthy());
    expect(screen.getByText("B-ab12cd")).toBeTruthy(); // confirmation card reference
    expect(screen.getByText("book_appointment")).toBeTruthy(); // intent chip
    expect(onBookingCreated).toHaveBeenCalledTimes(1);
  });

  it("fires onBookingCreated zero times when no booking is created", async () => {
    const onBookingCreated = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(200, chatResponse({ reply: "Sure — which day?", booking_created: null, intent: "book_appointment" }))),
    );

    render(<ChatPanel onBookingCreated={onBookingCreated} />);
    await send("Book a checkup");

    await waitFor(() => expect(screen.getByText(/which day\?/)).toBeTruthy());
    expect(onBookingCreated).not.toHaveBeenCalled();
    expect(screen.queryByText(/Booking confirmed/)).toBeNull(); // no confirmation card
  });

  it("surfaces a failed /api/chat as an error bubble (P7)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, { detail: "AI service unavailable: connection refused" })));

    render(<ChatPanel onBookingCreated={vi.fn()} />);
    await send("hello");

    await waitFor(() => expect(screen.getByText(/AI service unavailable/)).toBeTruthy());
    // input is re-enabled after the failure
    expect((screen.getByLabelText("Message") as HTMLInputElement).disabled).toBe(false);
  });
});
