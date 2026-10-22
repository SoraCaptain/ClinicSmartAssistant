"use client";

import { useEffect, useRef, useState } from "react";
import { postChat } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import type { ChatMessage } from "@/lib/types";
import MessageBubble from "./MessageBubble";

const GREETING: ChatMessage = {
  role: "assistant",
  content:
    "Hi John! I can answer questions about our clinics, doctors and treatments, " +
    "check your existing bookings, or book a new appointment for you. How can I help?",
};

export default function ChatPanel({ onBookingCreated }: { onBookingCreated?: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionRef.current = getSessionId();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages]);

  async function send(): Promise<void> {
    const text = input.trim();
    if (!text || busy) return;
    if (!sessionRef.current) sessionRef.current = getSessionId();
    setInput("");
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    try {
      const res = await postChat(sessionRef.current, text);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.reply,
          intent: res.intent,
          booking: res.booking_created ?? undefined,
        },
      ]);
      if (res.booking_created) onBookingCreated?.();
    } catch (err) {
      // P7 and any backend error surface verbatim in the chat — no canned fallback
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: err instanceof Error ? err.message : String(err),
          isError: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex h-[70vh] min-h-[480px] flex-col rounded-xl bg-slate-100 p-4 shadow-sm ring-1 ring-slate-200">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Assistant
      </h2>
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder={busy ? "Assistant is thinking…" : "Ask about treatments, doctors, or book an appointment…"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          aria-label="Message"
        />
        <button
          type="submit"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy || input.trim().length === 0}
        >
          {busy ? "…" : "Send"}
        </button>
      </form>
    </section>
  );
}
