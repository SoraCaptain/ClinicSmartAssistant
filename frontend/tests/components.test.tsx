import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BookingsPanel from "@/components/BookingsPanel";
import ChatPanel from "@/components/ChatPanel";
import SessionSidebar from "@/components/SessionSidebar";
import SummarizerTab from "@/components/SummarizerTab";
import Home from "@/app/page";
import type { BookingJoined, ChatHistoryMessage, ChatResponse, ChatSessionSummary, PatientContext } from "@/lib/types";

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
    // wait for the session's history fetch to settle — sending is gated on it
    await waitFor(() =>
      expect((screen.getByLabelText("Message") as HTMLInputElement).disabled).toBe(false),
    );
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: message } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  }

  // History fetch (404 = fresh session → greeting) must not collide with the
  // POST mock: route by URL like the Home tests do.
  function stubFetch(POST: () => Response) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string | URL) =>
        Promise.resolve(
          String(url).includes("/messages") ? jsonResponse(404, { detail: "Unknown session" }) : POST(),
        ),
      ),
    );
  }

  it("renders reply + confirmation card and fires onBookingCreated exactly once when a booking is created", async () => {
    const onBookingCreated = vi.fn();
    stubFetch(() => jsonResponse(200, chatResponse()));

    render(<ChatPanel sessionId="s1" onBookingCreated={onBookingCreated} />);
    await send("Book a general checkup");

    await waitFor(() => expect(screen.getByText(/You're booked!/)).toBeTruthy());
    expect(screen.getByText("B-ab12cd")).toBeTruthy(); // confirmation card reference
    expect(screen.getByText("book_appointment")).toBeTruthy(); // intent chip
    expect(onBookingCreated).toHaveBeenCalledTimes(1);
  });

  it("fires onBookingCreated zero times when no booking is created", async () => {
    const onBookingCreated = vi.fn();
    stubFetch(() =>
      jsonResponse(200, chatResponse({ reply: "Sure — which day?", booking_created: null, intent: "book_appointment" })),
    );

    render(<ChatPanel sessionId="s1" onBookingCreated={onBookingCreated} />);
    await send("Book a checkup");

    await waitFor(() => expect(screen.getByText(/which day\?/)).toBeTruthy());
    expect(onBookingCreated).not.toHaveBeenCalled();
    expect(screen.queryByText(/Booking confirmed/)).toBeNull(); // no confirmation card
  });

  it("surfaces a failed /api/chat as an error bubble (P7)", async () => {
    stubFetch(() => jsonResponse(503, { detail: "AI service unavailable: connection refused" }));

    render(<ChatPanel sessionId="s1" onBookingCreated={vi.fn()} />);
    await send("hello");

    await waitFor(() => expect(screen.getByText(/AI service unavailable/)).toBeTruthy());
    // input is re-enabled after the failure
    expect((screen.getByLabelText("Message") as HTMLInputElement).disabled).toBe(false);
  });
  it("shows only the greeting for a session with no persisted turns", async () => {
    stubFetch(() => jsonResponse(200, chatResponse()));

    render(<ChatPanel sessionId="s-fresh" onBookingCreated={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText(/Hi John! I can answer questions/)).toBeTruthy(),
    );
    expect((screen.getByLabelText("Message") as HTMLInputElement).disabled).toBe(false);
  });

  it("loads the persisted transcript for an old session (card + intent chip replayed)", async () => {
    const history: ChatHistoryMessage[] = [
      { id: 1, session_id: "s-old", role: "user", content: "Book a checkup please", intent: null, booking: null, created_at: "2026-10-22T09:00:00Z" },
      {
        id: 2,
        session_id: "s-old",
        role: "assistant",
        content: "You're booked!",
        intent: "book_appointment",
        booking: {
          booking_id: "B-old1",
          patient_id: "P001",
          doctor_id: "D101",
          treatment_id: "T001",
          booking_date: "2026-11-20",
          booking_time: "14:00:00",
          status: "Confirmed",
          notes: null,
          created_at: "2026-10-22T09:00:00Z",
          source: "chatbot",
        },
        created_at: "2026-10-22T09:00:05Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(200, history)),
    );

    render(<ChatPanel sessionId="s-old" onBookingCreated={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Book a checkup please")).toBeTruthy());
    expect(screen.getByText(/You're booked!/)).toBeTruthy();
    expect(screen.getByText("B-old1")).toBeTruthy(); // confirmation card replayed
    expect(screen.getByText("book_appointment")).toBeTruthy(); // intent chip replayed
  });

  it("shows an error bubble when history fails to load (not on a fresh 404)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(503, { detail: "AI service unavailable" })),
    );

    render(<ChatPanel sessionId="s-old" onBookingCreated={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/Couldn't load this session's history/)).toBeTruthy());
    expect(screen.queryByText(/Hi John!/)).toBeNull(); // greeting replaced, not faked
  });

  it("continues an old session: POSTs with its session_id and fires onTurnDone", async () => {
    const onTurnDone = vi.fn();
    const fetchMock = vi.fn().mockImplementation((url: string | URL) =>
      Promise.resolve(
        String(url).includes("/messages")
          ? jsonResponse(404, { detail: "Unknown session" })
          : jsonResponse(200, chatResponse({ reply: "Sure, continuing." })),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatPanel sessionId="s-old" onTurnDone={onTurnDone} onBookingCreated={vi.fn()} />);
    await send("and one more thing");

    await waitFor(() => expect(screen.getByText(/Sure, continuing\./)).toBeTruthy());
    const postCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/chat"));
    expect(JSON.parse(postCall![1].body)).toEqual({ session_id: "s-old", message: "and one more thing" });
    expect(onTurnDone).toHaveBeenCalledTimes(1);
  });
  it("a mid-flight session switch still refreshes the sidebar and never leaks the reply", async () => {
    let release: (v: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (release = resolve));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string | URL) =>
        String(url).includes("/messages")
          ? jsonResponse(404, { detail: "Unknown session" })
          : pending, // POST /api/chat hangs until we release it
      ),
    );
    const onTurnDone = vi.fn();
    const view = render(<ChatPanel sessionId="s-a" onTurnDone={onTurnDone} onBookingCreated={vi.fn()} />);
    await waitFor(() => expect((screen.getByLabelText("Message") as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "slow turn" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    view.rerender(<ChatPanel sessionId="s-b" onTurnDone={onTurnDone} onBookingCreated={vi.fn()} />); // switch away
    release(jsonResponse(200, chatResponse({ reply: "reply for session A" })));

    await waitFor(() => expect(onTurnDone).toHaveBeenCalledTimes(1)); // turn persisted → sidebar refreshed
    await waitFor(() =>
      expect((screen.getByLabelText("Message") as HTMLInputElement).disabled).toBe(false),
    );
    expect(screen.queryByText("reply for session A")).toBeNull(); // no leak into session B's view
    expect(screen.queryByText("slow turn")).toBeNull();
  });
});

describe("SessionSidebar", () => {
  const sessions: ChatSessionSummary[] = [
    { session_id: "s-new", title: "Knee pain question", created_at: "2026-10-23T09:00:00Z", updated_at: "2026-10-23T10:00:00Z" },
    { session_id: "s-old", title: "Booked a checkup", created_at: "2026-10-22T09:00:00Z", updated_at: "2026-10-22T09:05:00Z" },
  ];

  it("lists sessions and marks the active one", () => {
    render(
      <SessionSidebar sessions={sessions} activeId="s-old" onSelect={() => {}} onNew={() => {}} />,
    );

    expect(screen.getByText("Knee pain question")).toBeTruthy();
    const active = screen.getByRole("button", { name: /Booked a checkup/ });
    expect(active.getAttribute("aria-current")).toBe("true");
    expect(screen.getByRole("button", { name: /Knee pain question/ }).getAttribute("aria-current")).toBeNull();
  });

  it("fires onSelect with the session id and onNew for the new-session button", () => {
    const onSelect = vi.fn();
    const onNew = vi.fn();
    render(<SessionSidebar sessions={sessions} activeId={null} onSelect={onSelect} onNew={onNew} />);

    fireEvent.click(screen.getByRole("button", { name: /Knee pain question/ }));
    expect(onSelect).toHaveBeenCalledWith("s-new");

    fireEvent.click(screen.getByRole("button", { name: "+ New session" }));
    expect(onNew).toHaveBeenCalledTimes(1);
  });

  it("shows the empty hint when there are no sessions yet", () => {
    render(<SessionSidebar sessions={[]} activeId={null} onSelect={() => {}} onNew={() => {}} />);

    expect(screen.getByText(/No past sessions yet/)).toBeTruthy();
  });

  it("surfaces a failed sessions fetch instead of faking an empty list", () => {
    render(
      <SessionSidebar
        sessions={[]}
        activeId={null}
        onSelect={() => {}}
        onNew={() => {}}
        error="HTTP 503 Service Unavailable"
      />,
    );

    expect(screen.getByText(/Couldn't load sessions: HTTP 503/)).toBeTruthy();
    expect(screen.queryByText(/No past sessions yet/)).toBeNull();
  });
});

describe("SummarizerTab", () => {
  const SUMMARY = {
    chief_complaint: "Left knee pain for two weeks.",
    diagnosis: "Patellofemoral pain syndrome.",
    medication: "Ibuprofen 400mg twice daily for 5 days.",
    doctor_instructions: "Avoid running for one week.",
  };

  async function submit() {
    fireEvent.change(screen.getByLabelText("Transcript"), {
      target: { value: "Patient: my left knee hurts. Doctor: take ibuprofen and rest." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Summarize" }));
  }

  it("renders all four clinical fields from POST /api/summarize/transcript", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, SUMMARY)));

    render(<SummarizerTab />);
    await submit();

    for (const value of Object.values(SUMMARY)) {
      await waitFor(() => expect(screen.getByText(value)).toBeTruthy());
    }
    expect(screen.getByText("Chief complaint")).toBeTruthy();
    expect(screen.getByText("Doctor instructions")).toBeTruthy();
  });

  it("surfaces the backend error verbatim with a retry (fail loud)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, { detail: "AI service unavailable: connection refused" })));

    render(<SummarizerTab />);
    await submit();

    await waitFor(() => expect(screen.getByText(/AI service unavailable/)).toBeTruthy());
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect((screen.getByLabelText("Transcript") as HTMLTextAreaElement).disabled).toBe(false);
  });

  it("keeps Summarize disabled for an empty transcript", () => {
    render(<SummarizerTab />);

    expect((screen.getByRole("button", { name: "Summarize" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("BookingsPanel bare mode", () => {
  it("hides its own header when the tab bar labels the pane (refresh stays)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, [joinedBooking()])));

    render(<BookingsPanel bare />);

    await waitFor(() => expect(screen.getByText("General Checkup")).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "My bookings" })).toBeNull();
    expect(screen.getByRole("button", { name: /Refresh/ })).toBeTruthy();
  });
});

describe("Home (right pane tabs)", () => {
  const context: PatientContext = {
    profile: {
      patient_id: "P001",
      first_name: "John",
      last_name: "Doe",
      dob: "1988-05-14",
      gender: "Male",
      phone: "+1-555-018-3311",
      email: "john.doe@example.com",
      known_allergies: "Penicillin, Peanuts",
      emergency_contact: "Jane Doe (Spouse) - +1-555-018-3312",
    },
    treatment_history: [],
    upcoming_bookings: [],
  };

  it("switches the right pane between bookings and summarizer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url) => {
        const u = String(url);
        if (u.includes("/api/patients/")) return Promise.resolve(jsonResponse(200, context));
        if (u.includes("/messages")) return Promise.resolve(jsonResponse(404, { detail: "Unknown session" }));
        if (u.includes("/api/chat/sessions")) return Promise.resolve(jsonResponse(200, []));
        return Promise.resolve(jsonResponse(200, [joinedBooking()]));
      }),
    );

    render(<Home />);

    await waitFor(() => expect(screen.getByText("General Checkup")).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "My bookings" })).toBeNull(); // bare: tab bar labels the pane
    fireEvent.click(screen.getByRole("tab", { name: "Summarizer" }));
    expect(screen.getByLabelText("Transcript")).toBeTruthy();
    expect(screen.queryByText("General Checkup")).toBeNull(); // bookings unmounted on the other tab
  });

  it("reopens an old session from the sidebar and starts a fresh one on demand", async () => {
    const sessions: ChatSessionSummary[] = [
      { session_id: "s-old", title: "Old knee chat", created_at: "2026-10-22T09:00:00Z", updated_at: "2026-10-22T09:05:00Z" },
    ];
    const oldTranscript: ChatHistoryMessage[] = [
      { id: 1, session_id: "s-old", role: "user", content: "My knee hurts when I run", intent: null, booking: null, created_at: "2026-10-22T09:00:00Z" },
      { id: 2, session_id: "s-old", role: "assistant", content: "Let's look at joint & pain options.", intent: "qa", booking: null, created_at: "2026-10-22T09:00:05Z" },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url) => {
        const u = String(url);
        if (u.includes("/api/patients/")) return Promise.resolve(jsonResponse(200, context));
        if (u.includes("/s-old/messages")) return Promise.resolve(jsonResponse(200, oldTranscript));
        if (u.includes("/messages")) return Promise.resolve(jsonResponse(404, { detail: "Unknown session" }));
        if (u.includes("/api/chat/sessions")) return Promise.resolve(jsonResponse(200, sessions));
        return Promise.resolve(jsonResponse(200, []));
      }),
    );

    render(<Home />);

    // sidebar lists the persisted session; clicking it loads its transcript
    fireEvent.click(await screen.findByRole("button", { name: /Old knee chat/ }));
    expect(await screen.findByText("My knee hurts when I run")).toBeTruthy();
    expect(screen.getByText(/joint & pain options/)).toBeTruthy();
    expect(localStorage.getItem("clinicpilot-session-id")).toBe("s-old"); // selection survives reload

    // a new session clears back to the greeting without the old transcript
    fireEvent.click(screen.getByRole("button", { name: "+ New session" }));
    await waitFor(() => expect(screen.getByText(/Hi John! I can answer questions/)).toBeTruthy());
    expect(screen.queryByText("My knee hurts when I run")).toBeNull();
  });
});
