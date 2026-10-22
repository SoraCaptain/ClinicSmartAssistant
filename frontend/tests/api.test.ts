import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE, getBookings, getPatientContext, postChat } from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("postChat POSTs {session_id, message} to /api/chat and returns the parsed reply", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { reply: "hi", intent: "general", booking_created: null, session_id: "s1" }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await postChat("s1", "hello");

    expect(res.reply).toBe("hi");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/chat`,
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: "s1", message: "hello" }),
      }),
    );
  });

  it("postChat surfaces the backend {detail} on 503 (P7 fail-loud path)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(503, { detail: "AI service unavailable: connection refused" })),
    );

    await expect(postChat("s1", "hello")).rejects.toThrow(
      "AI service unavailable: connection refused",
    );
  });

  it("getBookings queries by patient_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await getBookings("P001");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/api/bookings?patient_id=P001`);
  });

  it("getPatientContext hits the context endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { profile: null, treatment_history: [], upcoming_bookings: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getPatientContext("P001");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/api/patients/P001/context`);
  });
});
