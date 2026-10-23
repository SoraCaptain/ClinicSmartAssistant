# ClinicPilot AI — Technical Documentation (as built)

Status: **implemented** (evolved from `DESIGN.md`, the pre-implementation contract; behavior pins carried over verbatim).

## 1. Goal & Non-Goals

**Goal.** An end-to-end MVP where a patient (fixed demo identity `P001`, John Doe) converses with an AI assistant that (a) answers clinic/doctor/treatment questions with grounded recommendations, (b) reads the patient's existing bookings, and (c) completes a new booking through parameter extraction and an agent-triggered REST call — with the new booking immediately visible in the UI. Bonus: a transcript summarizer.

**Non-goals (MVP)** — each with its upgrade path where relevant:

- Authentication / RBAC / multi-tenant patients (assignment simplifies to one preloaded patient).
- Schedule-conflict / overbooking validation (all slots assumed available).
- Streaming responses (SSE through two services + Next; plain request/response for MVP).
- Embeddings / vector store — the corpus is ~11 rows; structured retrieval is deterministic and exact. Upgrade path: same tool signatures backed by pgvector, invisible to the graph.
- Alembic migrations (`metadata.create_all` + idempotent seed suffices at demo grade).
- Postgres-backed LangGraph checkpointer (in-process `InMemorySaver`; single ai-service replica).
- Self-hosted Langfuse stack (cloud keys only).
- K8s production hardening (HPA, PDBs, StatefulSet Postgres, NetworkPolicies — manifests are demo-grade).

## 2. Architecture

```
┌──────────────┐  POST /api/chat (BFF proxy)  ┌──────────────┐
│   Next.js    │ ────────────────────────────► │   backend    │ ◄───┐
│   :3000      │ ◄──────────────────────────── │   FastAPI    │     │ REST tools (httpx)
│ chat +       │   GET /api/bookings etc.      │ SQLAlchemy   │     │ search_doctors / get_bookings /
│ bookings +   │                               │ PostgreSQL   │     │ create_booking / patient context
│ summarizer   │                               └──────┬───────┘     │
└──────────────┘                                      │ /chat proxy │
                                                      ▼             │
                                               ┌──────────────┐     │
                                               │  ai-service  │ ────┘
                                               │ LangGraph    │ ──► Langfuse (traces, tokens, cost)
                                               │   :8001      │
                                               └──────────────┘
```

**Why two Python services** (matches the assignment's suggested layout):

- The assignment pins `POST /api/chat` on the *backend* which "forwards requests to the AI engine" — backend is the BFF; ai-service owns all LLM orchestration.
- Agent tools call the backend over **REST (httpx)** — literally satisfying "must trigger a REST API endpoint … to save the new booking", and keeping ai-service stateless and DB-free (P3).
- Each service is independently testable (backend with sqlite + fakes; ai-service with scripted fake LLM chains + faked tools) — which is how the test suites run with zero network.

**Why classifier-first supervision, not free-form ReAct.** Deterministic routing → specialized nodes makes multi-turn slot-filling, tests, and Langfuse traces legible. The booking flow *is* a state machine (missing slots → ask → confirm → execute); LangGraph makes that explicit. Graph shape: `START → classify_intent → {qa | bookings | booking nodes | general} → END`, with the booking flow as flat nodes on the same graph.

## 3. Repository Layout (as built)

```
ClinicSmartAssistant/
├── ai-service/                  # AI engine (Python 3.11, FastAPI + LangGraph)
│   ├── app/
│   │   ├── main.py              # POST /chat, POST /summarize, GET /health (backend probe)
│   │   ├── runtime.py           # compiled graph + InMemorySaver; per-turn patient context (P8)
│   │   ├── summarizer.py        # transcript → 4 clinical fields (bonus)
│   │   ├── core/config.py       # pydantic-settings
│   │   ├── schemas/             # chat.py, summarize.py
│   │   └── agent/
│   │       ├── llm.py           # ChatOpenAI factory (OPENAI_BASE_URL → any provider)
│   │       ├── state.py         # ClinicGraphState (TypedDict)
│   │       ├── graph.py         # build_clinic_graph()
│   │       ├── prompts.py       # all node prompt templates
│   │       ├── nodes/           # classifier, qa, bookings_query, booking_flow, general
│   │       ├── tools/           # catalog / booking / patient tools over backend REST
│   │       └── observability/tracing.py   # Langfuse v4 singleton, fail-soft
│   └── tests/                   # scripted fake chains; no network, no API key
├── backend/                     # API + persistence (FastAPI + SQLAlchemy)
│   ├── app/{main,database}.py   # lifespan: create_all + seed-if-empty (P4)
│   ├── app/models/              # 6 tables mirroring the CSVs
│   ├── app/routers/             # health, chat, bookings, catalog, patients, summarize
│   ├── app/services/            # booking/catalog services, ai_client (proxy), seed_service
│   ├── scripts/seed.py          # idempotent CSV seed (`python -m` entrypoint)
│   └── tests/                   # sqlite-backed pytest
├── frontend/                    # Next.js 14 App Router + Tailwind
│   ├── src/app/page.tsx         # three panes; right pane tabbed (bookings | summarizer)
│   ├── src/components/          # ChatPanel, MessageBubble, BookingsPanel, PatientCard, SummarizerTab
│   └── src/lib/                 # typed api client, wire types, session id
├── mock-data/                   # provided CSVs
├── k8s/                         # 00-namespace … 07-ingress (apply in filename order)
├── docker-compose.yml           # postgres → backend (seeded) → ai → frontend, healthchecked
├── Makefile                     # dev-*, test, compose-*, k8s-*
└── README.md                    # cold-setup walkthrough
```

## 4. Behavior Pins (the contract, as enforced)

| # | Pin | Enforced by |
|---|-----|-------------|
| P1 | Every turn re-classified against full state; intent may switch mid-session; a pending draft never traps non-booking turns | `nodes/classifier.py` sees `messages` + `booking_draft` every turn; routed per-intent (`tests/test_graph_routing.py`) |
| P2 | `create_booking` fires only with doctor+treatment+date+time resolved AND explicit confirmation of a rendered summary; exactly once | booking-flow confirm gate (`nodes/booking_flow.py`; `tests/test_booking_flow.py`) |
| P3 | ai-service never touches the DB — backend REST tools only | all tools go through `agent/tools/client.py` (httpx) |
| P4 | Seed idempotent: upsert-by-PK, skip-if-populated; FK-safe table order under Postgres | `scripts/seed.py` + `tests/test_seed.py` (incl. `PRAGMA foreign_keys=ON` regression) |
| P5 | `GET /api/bookings?patient_id=P001` reflects an AI booking immediately | plain committed writes; joined read model (`tests/test_bookings.py`) + UI refresh-on-`booking_created` |
| P6 | Langfuse optional: no keys → tracing off, `/chat` unaffected; keys → every chat traced with user/session/intent + token/cost per LLM call | `observability/tracing.py` fail-soft root (`tests/test_tracing.py`) |
| P7 | ai-service unreachable → backend `/api/chat` (and `/api/summarize/transcript`) returns 503 with clear detail; upstream errors → 502 | `routers/chat.py`, `routers/summarize.py` (`tests/test_chat.py`, `tests/test_summarize.py`) |
| P8 | Patient context injected into every graph run for the resolved `patient_id` (default `P001` via `DEFAULT_PATIENT_ID`) | `runtime.handle_chat` fetches `GET /api/patients/{id}/context` per turn |

## 5. AI Service — LangGraph

### 5.1 State (`agent/state.py`, TypedDict)

`session_id, patient_id, patient_context, messages, user_message, intent, retrieved, booking_draft, booking_created, reply` — undeclared keys are dropped by LangGraph; `total=False`.

### 5.2 Booking flow

```
extract_slots ── missing? ──► ask_missing (turn ends; draft persists via checkpointer)
      │ complete
      ▼
confirm_summary (render doctor+treatment+date+time+fee; awaiting_confirmation; turn ends)
      ▼ next turn routed back into booking nodes while awaiting_confirmation
user affirmed? ── yes ──► execute_booking (POST /api/bookings) → success_reply; draft cleared
      └── no / changed mind ──► extract_slots (re-enter with corrections)
```

- The classifier sees `booking_draft`: bare "yes"/"no" while `awaiting_confirmation` routes to booking nodes, never `general`; unrelated messages classify on their own merits.
- Multi-turn memory: compiled graph + `InMemorySaver`, `thread_id = session_id`; the frontend mints a `crypto.randomUUID` session id (with a `getRandomValues` fallback for non-secure contexts) and reuses it.
- Slot extraction uses structured output, ISO-normalized (`booking_date` `YYYY-MM-DD`, `booking_time` `HH:MM`). A treatment-only mention triggers a doctor recommendation step (specialty/category match) and asks the user to choose; clinic is derived from the doctor.

### 5.3 Retrieval ("RAG") over the tiny corpus

`search_treatments(query)`, `search_doctors(specialty?)`, `get_clinics()` call backend catalog endpoints doing case-insensitive contains-match over `specialty/category/name/bio/instructions`. Retrieved rows are injected into the `qa_answer` prompt; replies cite row IDs (`T005`, `D104`) and ground on retrieved rows only. On an 11-row corpus this is exact and testable; embeddings would add infrastructure and non-determinism with zero recall benefit.

### 5.4 Tools (`@tool`, httpx → backend)

| Tool | Backend call | Used by |
|------|--------------|---------|
| `get_patient_context()` | `GET /api/patients/{id}/context` | runtime (P8) |
| `search_treatments(query)` | `GET /api/treatments?search=` | qa |
| `search_doctors(specialty?)` | `GET /api/doctors?specialty=` | qa, booking nodes |
| `get_clinics(clinic_id?)` | `GET /api/clinics` | qa |
| `get_my_bookings()` | `GET /api/bookings?patient_id=` | bookings_query |
| `create_booking(doctor_id, treatment_id, booking_date, booking_time, notes?)` | `POST /api/bookings` | booking nodes (P2) |

Tool errors surface as readable text to the LLM (fail loud, no silent fallbacks).

### 5.5 LLM & observability

- `ChatOpenAI` from env: `OPENAI_API_KEY`, `OPENAI_BASE_URL` (any OpenAI-compatible provider), `LLM_MODEL` (one model for everything).
- **Provider-compat note (hard-won):** structured-output chains pin `method="function_calling"` — the langchain-default `json_schema` response_format is rejected by several OpenAI-compatible providers (DeepSeek 400); and `LLM_MODEL` must be a non-thinking model where the provider distinguishes (thinking endpoints reject forced `tool_choice`).
- Langfuse v4 (OTel): one root observation per `/chat` (trace `clinic-chat`) and per `/summarize` (`clinic-summarize`), LangChain `CallbackHandler` on each LLM chain for tokens/cost, resolved intent tagged via `propagate_attributes`; clean lifespan shutdown; entirely fail-soft — absent keys or a Langfuse failure degrade to an untraced request, never an error response (P6).

### 5.6 Health (k8s probes)

`GET /health` probes the backend's `/api/health`: `200 {"status":"ok","backend":"up"}` or `503 {"status":"degraded","backend":"down"}` — an ai instance that cannot reach its tools should not take traffic (readiness). `GET /livez` is process-only liveness: a backend outage must degrade readiness without restarting the pod, which would wipe the in-process conversation checkpointer mid-session.

## 6. Backend API Contracts

Pydantic validation; errors as `{detail}`; 422 on validation, 404 unknown ids, 503 from the proxies when ai-service is down (P7), 502 on upstream errors.

| Endpoint | Contract |
|----------|----------|
| `GET /api/health` | `{status:"ok"\|"degraded", db:"up"\|"down"}` |
| `POST /api/chat` | `{session_id, message, patient_id?}` → `{reply, intent, booking_created?, session_id}`; proxies to ai-service `POST /chat`; on success persists the turn (§7 chat tables) |
| `GET /api/bookings?patient_id=` | joined read model: booking + doctor name/specialty + treatment name + clinic name + status/date/time/notes/created_at (P5) |
| `POST /api/bookings` | `{patient_id, doctor_id, treatment_id, booking_date (YYYY-MM-DD), booking_time (HH:MM), notes?}` → `201` + persisted booking; FK existence + format validation; no conflict check; server-generated `booking_id` = `B` + uuid hex prefix |
| `GET /api/doctors?specialty=` `GET /api/treatments?search=` `GET /api/clinics` | catalog reads (§5.3 contains-match) |
| `GET /api/patients/{id}/context` | profile + allergies + treatment history + upcoming bookings (P8 payload) |
| `POST /api/summarize/transcript` | bonus: `{transcript}` → `{chief_complaint, diagnosis, medication, doctor_instructions}` (proxied to ai-service `/summarize`) |
| `GET /api/chat/sessions` | multi-session chat: `[{session_id, title, created_at, updated_at}]`, most recently active first; title = first user message (≤60 chars) |
| `GET /api/chat/sessions/{session_id}/messages` | persisted transcript `[{id, session_id, role, content, intent, booking, created_at}]` in order; 404 unknown session |

No inter-service auth (internal network); noted for k8s hardening.

## 7. Database Schema (PostgreSQL 16)

Six tables mirror the CSVs 1:1 (snake_case, string PKs `C001/D101/T005/P001/B1004/H9001`), plus booking audit columns, plus the two chat-history tables (multi-session chat):

```
clinics(clinic_id PK, clinic_name, address, phone, operating_hours, cancellation_policy, emergency_instructions)
doctors(doctor_id PK, clinic_id FK, full_name, specialty, languages_spoken, consultation_fee_usd Numeric(10,2), bio)
treatments(treatment_id PK, treatment_name, category, duration_minutes int, price_usd Numeric(10,2), pre_treatment_instructions)
patients(patient_id PK, first_name, last_name, dob, gender, phone, email, known_allergies, emergency_contact)
patient_bookings(booking_id PK, patient_id FK, doctor_id FK, treatment_id FK, booking_date date, booking_time time,
                 status default 'Confirmed', notes, created_at timestamptz default now(), source default 'chatbot')
patient_treatment_history(record_id PK, patient_id FK, doctor_id FK, visit_date date,
                          chief_complaint, diagnosis, prescribed_medication, doctor_notes)
chat_sessions(session_id PK, patient_id default 'P001', title varchar(60), created_at timestamptz, updated_at timestamptz)
chat_messages(id PK autoincrement, session_id FK→chat_sessions, role, content, intent nullable,
              booking_json text nullable, created_at timestamptz)
```

Multi-session chat: `chat_sessions` rows are created lazily by a session's first *successful* chat turn
(failed turns persist nothing — P7 stays fail-loud and the sidebar never lists empty sessions); each turn
appends user + assistant rows (`booking_json` snapshots `booking_created` so the confirmation card replays
from history) and bumps `updated_at`. The backend owns the durable transcript; agent memory stays in the
ai-service thread checkpointer — after an ai-service restart an old thread resumes empty while its
transcript still renders (demo-grade `MemorySaver` tradeoff). A persistence failure after a successful
turn degrades to a logged transcript gap — the turn is still served so a retry can't double-book.

Seed: `scripts/seed.py` reads `mock-data/*.csv` (stdlib `csv` — the files have no trailing newline), upserts by PK, skips populated tables, and flushes per table in FK order (single-`commit` unit-of-work ordering is not deterministic on Postgres — regression-tested against sqlite with `PRAGMA foreign_keys=ON`). Demo data anchor: 2 clinics, 4 doctors, 5 treatments, 3 patients, 4 bookings (P001: B1001 General Checkup 2026-11-05, B1004 knee consult 2026-11-15), 2 history rows; P001 allergies: Penicillin, Peanuts.

## 8. Frontend (Next.js 14, App Router, Tailwind)

Single page `/`, four panes:

- **SessionSidebar** — "New session" button + persisted session list (`GET /api/chat/sessions`, refreshed after each turn); clicking a session loads its transcript (`GET /api/chat/sessions/{id}/messages`; 404 → greeting only) and chatting continues that session's agent thread. Old sessions are never deleted.
- **PatientCard** — P001 profile + allergy badges (from `/api/patients/{id}/context`).
- **ChatPanel** — message list + input; `POST /api/chat`; renders `booking_created` as a confirmation card (replayed from history too), shows an intent chip, and bumps the shared refresh key so bookings/patient card refetch without polling (P5 visible live). Errors surface verbatim (P7); the greeting and error bubbles are client-only.
- **Right pane, tabbed** — **BookingsPanel** (`GET /api/bookings?patient_id=P001`, refresh button + auto-refresh on `booking_created`) and the bonus **SummarizerTab** (textarea → `POST /api/summarize/transcript` → four-field structured view).

Active `session_id`: uuid persisted in localStorage (`getSessionId`; selecting a session rewrites it via
`setSessionId`, "New session" remints via `newSessionId`); `crypto.randomUUID()` with a `getRandomValues`
v4 fallback (non-secure contexts). API base: `NEXT_PUBLIC_API_URL`, **inlined at build time** (default
`http://localhost:8000` for dev/compose; the k8s image builds with the ingress origin).

## 9. DevOps

**docker-compose.yml** (dev + demo): `postgres:16-alpine` (healthcheck `pg_isready`, not published to the host) → `backend` (depends healthy; CMD runs the idempotent seed then uvicorn) → `ai` (depends backend healthy) → `frontend`. Env from root `.env`; Langfuse keys pass through as optional.

**k8s/** (demo-grade, `kubectl apply -f k8s/` — files numbered for apply order): namespace `clinicpilot`; ConfigMap (service URLs, model, default patient); Secret (DB creds, `OPENAI_API_KEY`, Langfuse keys — placeholders to edit); Postgres Deployment + 1Gi PVC (readiness `pg_isready`; StatefulSet/cloud DB is the noted upgrade); backend + ai + frontend Deployments + ClusterIP Services; ai readiness on `/health` (backend-gated, §5.6) and liveness on `/livez` (process-only) — DESIGN §9 pinned both probes on `/health`, but a backend outage restarting the ai pod would wipe the in-memory checkpointer, so as-built the probes split; Ingress (nginx class, host `clinicpilot.local`) routing `/api`→backend and `/`→frontend. Images built by `make k8s-build` (`clinicpilot/{backend,ai,frontend}:latest`; the frontend build receives `K8S_FRONTEND_ORIGIN`, default `http://clinicpilot.local` — changing the host requires rebuilding that image).

## 10. Test Strategy

All suites run offline; `make test` runs everything.

- **backend** (pytest, sqlite via `DATABASE_URL` override): booking POST validation (bad FK / bad date → 422), seed idempotency + FK ordering (P4), joined read model (P5), catalog contains-match, chat proxy contract incl. P7 503/502, summarize proxy contract.
- **ai-service** (pytest, scripted fake chains patched at their consumer modules; tools faked at consumer modules): routing per intent + mid-session switches (P1), confirmation "yes"/"no" while draft pending (P1/P2), slots accumulate across turns, `create_booking` called once with the correct payload only after confirmation (P2/P3), out-of-scope refusal, missing-slot questions, P8 context injection, P6 tracing (off without keys / on with fakes / fail-soft), summarize roundtrip + validation.
- **frontend** (vitest + testing-library, fetch stubbed): panels render the wire contracts, error paths surface verbatim, `postChat`/`postSummarize` request shapes.

## 11. Implementation Slices (all shipped)

| # | Slice | Status |
|---|-------|--------|
| 1 | backend models + idempotent seed + bookings/catalog/patients endpoints + tests | ✅ |
| 2 | ai-service config/LLM/state/classifier/general + `/chat` + backend proxy (P7) | ✅ |
| 3 | booking nodes + slot extraction + confirm gate + `create_booking` tool | ✅ |
| 4 | qa node + catalog tools + patient context injection (P8) | ✅ |
| 5 | frontend chat + bookings + patient card | ✅ |
| 6 | Langfuse tracing (P6) + Dockerfiles + compose stack | ✅ |
| 7 | summarizer + k8s manifests + README/TECH_DOC | ✅ (this document) |
