import type { BookingOut, ChatMessage } from "@/lib/types";

const INTENT_STYLES: Record<string, string> = {
  qa: "bg-sky-100 text-sky-700",
  check_bookings: "bg-amber-100 text-amber-700",
  book_appointment: "bg-emerald-100 text-emerald-700",
  general: "bg-gray-200 text-gray-600",
};

function BookingCard({ booking }: { booking: BookingOut }) {
  return (
    <div className="mt-2 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm">
      <p className="mb-1 font-semibold text-emerald-800">✅ Booking confirmed</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-emerald-900">
        <dt className="text-emerald-700">Reference</dt>
        <dd className="font-mono">{booking.booking_id}</dd>
        <dt className="text-emerald-700">Doctor</dt>
        <dd>{booking.doctor_id}</dd>
        <dt className="text-emerald-700">Treatment</dt>
        <dd>{booking.treatment_id}</dd>
        <dt className="text-emerald-700">When</dt>
        <dd>
          {booking.booking_date} at {booking.booking_time.slice(0, 5)}
        </dd>
        <dt className="text-emerald-700">Status</dt>
        <dd>{booking.status}</dd>
      </dl>
    </div>
  );
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
          isUser
            ? "rounded-br-sm bg-blue-600 text-white"
            : message.isError
              ? "rounded-bl-sm border border-red-300 bg-red-50 text-red-700"
              : "rounded-bl-sm bg-white text-gray-800 shadow-sm ring-1 ring-gray-200"
        }`}
      >
        {!isUser && message.intent && (
          <span
            className={`mb-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
              INTENT_STYLES[message.intent] ?? INTENT_STYLES.general
            }`}
          >
            {message.intent}
          </span>
        )}
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.booking && <BookingCard booking={message.booking} />}
      </div>
    </div>
  );
}
