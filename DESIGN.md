# ClinicPilot AI — System Design

Status: **proposed** (names are provisional until the proving build; behavior pins are the contract).
Source of truth for implementation; refined into `TECH_DOC.md` at submission.

---

## 1. Goal & Non-Goals

**Goal.** An end-to-end MVP where a patient (fixed demo identity `P001`, John Doe) converses with an AI
assistant that (a) answers clinic/doctor/treatment questions with recommendations (RAG), (b) reads the
patient's existing bookings, and (c) completes a new booking through parameter extraction and an
agent-triggered REST call — with the new booking immediately visible in the UI.

**Non-goals (MVP).**

- Authentication / RBAC / multi-tenant patients (assignment explicitly simplifies to a single preloaded patient).
- Schedule-conflict / overbooking validation (assignment: assume all slots available).
- Streaming responses (SSE through two services + Next adds plumbing with no evaluation payoff; upgrade path noted).
- Embeddings / vector store (pgvector, Chroma) — corpus is 2 clinics + 4 doctors + 5 treatments ≈ 11 rows;
  structured retrieval is deterministic and fully accurate at this size. Upgrade path in §5.3.
- Alembic migrations (`metadata.create_all` + idempotent seed; LedgerMind-proven for demo grade).
- Postgres-backed LangGraph checkpointer (in-process `MemorySaver` suffices for a single-instance demo).
- Self-hosted Langfuse stack (ClickHouse/MinIO/Redis is heavier than the app; use Langfuse Cloud keys).
- K8s production hardening: HPA, PodDisruptionBudgets, StatefulSet Postgres, NetworkPolicies (manifests are demo-grade).

---

## 2. Architecture Overview

```
┌──────────────┐  POST /api/chat (BFF proxy)  ┌──────────────┐
│   Next.js    │ ────────────────────────────► │   backend    │ ◄───┐
│   :3000      │ ◄──────────────────────────── │ FastAPI:8000 │     │ REST tools (httpx)
│ chat +       │   GET /api/bookings etc.      │ SQLAlchemy   │     │ search_doctors / get_bookings /
│ bookings UI  │                               │ PostgreSQL   │     │ create_booking / patient ctx
└──────────────┘                               └──────┬───────┘     │
                                                      │ /chat proxy │
                                                      ▼             │
                                               ┌──────────────┐     │
                                               │  ai-service  │ ────┘
                                               │ LangGraph    │ ──► Langfuse (traces, tokens, cost)
                                               │ FastAPI:8001 │
                                               └──────────────┘
```

**Why two Python services** (matches the assignment's suggested repo layout):
- The assignment pins `POST /api/chat` on the *backend* which "forwards requests to the AI engine" — backend is
  the BFF; ai-service owns all LLM orchestration.
- Agent tools call the backend over **REST (httpx)** — literally satisfying "must trigger a REST API endpoint
  … to save the new booking", and keeping ai-service stateless and DB-free (pin P3).
- Each service is independently testable (backend with sqlite + fake ai-service; ai-service with fake LLM +
  fake backend) — this is where the 24h timeline is won or lost.
- Alternative rejected: single service with in-process tools (LedgerMind-style). Simpler, but self-HTTP or
  in-process calls blur the "AI engine ↔ API" boundary the assignment evaluates, and lose the REST-tooling story.

**Why classifier-first supervision, not free-form ReAct.** Deterministic routing → specialized nodes makes
multi-turn slot-filling, tests, and Langfuse traces legible. The booking flow *is* a state machine (missing
slots → ask → confirm → execute); LangGraph's job is to make that explicit. Proven shape:
LedgerMind `graphs/ledger_graph.py` (entry classifier + `NODE_SPECS` routing table).

---

## 3. Repository Structure

```
ClinicSmartAssistant/
├── ai-service/                     # AI engine (Python 3.11, FastAPI + LangGraph)
│   ├── app/
│   │   ├── main.py                 # FastAPI: POST /chat, POST /summarize, GET /health; lifespan
│   │   ├── core/config.py          # pydantic-settings
│   │   ├── schemas/chat.py         # ChatRequest / ChatResponse / BookingCreated
│   │   ├── runtime.py              # graph runtime: compiled app + MemorySaver, per-session thread
│   │   └── agent/
│   │       ├── llm.py              # ChatOpenAI factory (OPENAI_BASE_URL configurable → any provider)
│   │       ├── state.py            # ClinicGraphState (TypedDict)
│   │       ├── graph.py            # build_clinic_graph(): assembly entry point
│   │       ├── nodes/
│   │       │   ├── classifier.py   # structured-output intent classification (+ confirmation detection)
│   │       │   ├── qa.py           # retrieve → compose recommendation w/ cited IDs
│   │       │   ├── bookings_query.py
│   │       │   ├── booking_flow.py # booking nodes: extract slots → ask|confirm → execute
│   │       │   └── general.py      # smalltalk + out-of-scope refusal
│   │       ├── tools/
│   │       │   ├── catalog_tools.py    # search_treatments, search_doctors, get_clinics
│   │       │   ├── booking_tools.py    # get_my_bookings, create_booking
│   │       │   └── patient_tools.py    # get_patient_context (profile, allergies, history)
│   │       ├── prompts.py
│   │       └── observability/tracing.py  # Langfuse v4 singleton (LedgerMind pattern)
│   ├── tests/                      # fake-LLM graph tests (routing, slots, confirm gate)
│   ├── Dockerfile
│   └── pyproject.toml
├── backend/                        # API + persistence (Python 3.11, FastAPI + SQLAlchemy)
│   ├── app/
│   │   ├── main.py                 # lifespan: create_all + seed-if-empty; CORS; error middleware
│   │   ├── core/{config,logging}.py
│   │   ├── database.py
│   │   ├── models/                 # clinic, doctor, treatment, patient, booking, treatment_history
│   │   ├── schemas/                # pydantic request/response per router
│   │   ├── routers/                # health, chat, bookings, catalog, patients, summarize
│   │   └── services/               # booking_service, catalog_service (keyword search),
│   │                               # ai_client (httpx proxy), seed_service, summarize_service
│   ├── scripts/seed.py             # idempotent CSV seed (importable + `python -m` entrypoint)
│   ├── tests/                      # sqlite-backed pytest (validation, seed idempotency, joins)
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/                       # Next.js 14 App Router + Tailwind
│   ├── src/app/{page,layout}.tsx
│   ├── src/components/             # ChatPanel, MessageBubble, BookingsPanel, PatientCard, SummarizerTab
│   ├── src/lib/{api.ts, types.ts}  # typed client; session id (crypto.randomUUID, localStorage)
│   ├── Dockerfile                  # multi-stage → next standalone
│   └── package.json
├── mock-data/                      # provided CSVs (git mv dkl_ai_interview_data → mock-data)
├── k8s/                            # namespace, configmap, secret, postgres, backend, ai, frontend, ingress
├── docker-compose.yml              # postgres + backend + ai-service + frontend (healthchecked)
├── .env.example
├── Makefile                        # seed / dev-backend / dev-ai / dev-frontend / test
├── DESIGN.md → refined into TECH_DOC.md at submission
└── README.md
```

`dkl_ai_interview_data/` is renamed to `mock-data/` (assignment's suggested layout; seed reads from there).
The tree is the proposed layout — load-bearing modules (graph, nodes, tools, routers) are the contract;
exact file granularity may flex during implementation.

---

## 4. Behavior Pins (the contract)

| # | Pin |
|---|-----|
| P1 | Every chat turn is re-classified against the full conversation state; intent may switch mid-session (no sticky intent). A pending booking draft does not trap non-booking turns. |
| P2 | `create_booking` fires **only** when doctor + treatment + date + time are resolved **and** the user explicitly confirmed a rendered summary; exactly once per confirmation. |
| P3 | ai-service never touches the database — only via backend REST tools. |
| P4 | Seed is idempotent: re-running never duplicates rows (upsert-by-PK, skip-if-populated). |
| P5 | `GET /api/bookings?patient_id=P001` reflects an AI-created booking immediately after `POST /api/bookings` returns. |
| P6 | Langfuse is optional: absent keys → tracing off, `/chat` unaffected; present → every `/chat` traced with `user_id`, `session_id`, intent tag, token/cost per LLM call. |
| P7 | ai-service unreachable → backend `/api/chat` returns `503` with a clear detail (fail fast; no canned fallback). |
| P8 | Patient context (profile, allergies, treatment history, upcoming bookings) is injected into every graph run for the resolved `patient_id` (default `P001` via env `DEFAULT_PATIENT_ID`). |

## 5. AI Service — LangGraph Design

### 5.1 State (`agent/state.py`, TypedDict — LangGraph drops undeclared keys)

```python
class ClinicGraphState(TypedDict, total=False):
    session_id: str
    patient_id: str
    patient_context: dict        # profile, allergies, history (tool-fetched, runtime-injected)
    messages: list               # full conversation (checkpointer persists per thread)
    user_message: str
    intent: str                  # qa | check_bookings | book_appointment | general
    retrieved: list[dict]        # rows pulled by catalog tools for the answer
    booking_draft: dict          # {doctor_id?, treatment_id?, booking_date?, booking_time?, awaiting_confirmation: bool}
    booking_created: dict | None # persisted booking returned by create_booking
    reply: str                   # final assistant text for this turn
```

### 5.2 Graph topology

```
START → classify_intent ──(qa)────────────► qa_answer ──────────────┐
             │                                                              ├──► END
             ├──(check_bookings)──► bookings_answer ─────────────────┤
             ├──(book_appointment)─► booking nodes ────────────┤
             └──(general)─────────► general_reply ─────────────┘

booking nodes (flat, same graph; extract to a subgraph only if the first build wants it):
  extract_slots ── missing? ──► ask_missing (reply; turn ends, draft persists via checkpointer)
        │ complete
        ▼
  confirm_summary (render doctor+treatment+date+time+fee; set awaiting_confirmation; turn ends)
        ▼ next turn routed back into booking nodes while awaiting_confirmation
  user affirmed? ── yes ──► execute_booking (tool: POST /api/bookings) → success_reply; clear draft
        └── no / changed mind ──► extract_slots (re-enter with corrections)
```

- Classifier sees `booking_draft`; bare "yes"/"no" while `awaiting_confirmation` routes to the booking
  nodes (never `general`).
- Multi-turn memory: compiled graph + `MemorySaver` checkpointer, `thread_id = session_id`; the frontend
  mints `session_id` (uuid) and reuses it across turns.
- Slot extraction uses structured output (`doctor/treatment/date/time` + raw entities, ISO-normalized:
  `booking_date` `YYYY-MM-DD`, `booking_time` `HH:MM`). A treatment-only mention triggers a doctor
  recommendation step (specialty/category match) and asks the user to choose; clinic is derived from the doctor.

### 5.3 Retrieval ("RAG") over the tiny corpus

`search_treatments(query)`, `search_doctors(specialty?)`, `get_clinics()` call backend catalog endpoints that
filter by case-insensitive contains-match on `specialty`/`category`/`name`/`bio`/`instructions` — exact
recall is guaranteed on an 11-row corpus; no scoring machinery. Retrieved rows are injected into the
`qa_answer` prompt; the reply cites IDs (`T005`, `D104`) and must ground on retrieved rows only. Why not
embeddings: 11 rows — vector recall adds infra and non-determinism with zero benefit; structured search is
exact and testable. Upgrade path: same tool signature backed by pgvector, invisible to the graph.

### 5.4 Tools (LangChain `@tool`, httpx → backend)

| Tool | Backend call | Used by |
|------|--------------|---------|
| `get_patient_context()` | `GET /api/patients/{id}/context` | runtime (P8) |
| `search_treatments(query)` | `GET /api/treatments?search=` | qa |
| `search_doctors(specialty?)` | `GET /api/doctors?specialty=` | qa, booking nodes |
| `get_clinics(clinic_id?)` | `GET /api/clinics` | qa |
| `get_my_bookings()` | `GET /api/bookings?patient_id=` | bookings_query |
| `create_booking(doctor_id, treatment_id, booking_date, booking_time, notes?)` | `POST /api/bookings` | booking nodes (P2) |

Tool errors surface as readable text to the LLM (fail loud, no silent fallbacks); Langfuse spans record each call.

### 5.5 LLM & observability

- `ChatOpenAI` via env: `OPENAI_API_KEY`, `OPENAI_BASE_URL` (any OpenAI-compatible provider), `LLM_MODEL`
  (one model for everything; a cheaper classifier model is an upgrade if observed cost ever demands it).
- Langfuse v4 (OTel): root observation per `/chat` wrapping `graph.ainvoke`, LangChain `CallbackHandler`
  attached for token/cost, clean lifespan shutdown; disabled gracefully when keys absent (P6). Singleton
  client pattern: LedgerMind `app/agent/observability/tracing.py` (implementation detail lives there,
  not in this contract).

## 6. Backend API Contracts

All validation via pydantic; errors as RFC7807-ish `{detail}`; 422 on validation, 404 unknown ids, 503 from
the chat proxy when ai-service is down (P7).

| Endpoint | Contract |
|----------|----------|
| `GET /api/health` | `{status:"ok", db:"up"\|"down"}` (probe target) |
| `POST /api/chat` | req `{session_id, message, patient_id?}` → resp `{reply, intent, booking_created?, session_id}`; proxies to ai-service `POST /chat` |
| `GET /api/bookings?patient_id=` | joined read model for the UI: booking + doctor name/specialty + treatment name + clinic name + status/date/time/notes/created_at (P5) |
| `POST /api/bookings` | req `{patient_id, doctor_id, treatment_id, booking_date (YYYY-MM-DD), booking_time (HH:MM), notes?}` → `201` + persisted booking; FK existence + format validation; no conflict check; server-generated unique `booking_id` |
| `GET /api/doctors?specialty=` `GET /api/treatments?search=` `GET /api/clinics` | catalog reads (§5.3 contains-match) for the agent tools |
| `GET /api/patients/{id}/context` | profile + allergies + treatment history + upcoming bookings (P8 payload) |
| `POST /api/summarize/transcript` | bonus: `{transcript}` → `{chief_complaint, diagnosis, medication, doctor_instructions}` (proxied to ai-service `/summarize`) |

No inter-service auth (internal network); noted for k8s hardening in §9.

## 7. Database Schema (PostgreSQL 16)

Six tables mirror the CSVs 1:1 (snake_case, string PKs kept: `C001/D101/T005/P001/B1004/H9001`), plus
booking audit columns. `Numeric(10,2)` for fees/prices, `Date`/`Time` for date/time.

```
clinics(clinic_id PK, clinic_name, address, phone, operating_hours, cancellation_policy, emergency_instructions)
doctors(doctor_id PK, clinic_id FK→clinics, full_name, specialty, languages_spoken, consultation_fee_usd, bio)
treatments(treatment_id PK, treatment_name, category, duration_minutes int, price_usd, pre_treatment_instructions)
patients(patient_id PK, first_name, last_name, dob date, gender, phone, email, known_allergies, emergency_contact)
patient_bookings(booking_id PK, patient_id FK, doctor_id FK, treatment_id FK,
                 booking_date date, booking_time time, status varchar default 'Confirmed', notes text,
                 created_at timestamptz default now(), source varchar default 'chatbot')
patient_treatment_history(record_id PK, patient_id FK, doctor_id FK, visit_date date,
                          chief_complaint, diagnosis, prescribed_medication, doctor_notes)
```

New `booking_id`: server-generated, `B` + short uuid suffix (single mechanism, collision-free; sequential
`B1005`-style numbering deliberately not built). Seed: `scripts/seed.py` reads `mock-data/*.csv`, upserts by
PK, skips when table already populated (P4) — the seed tests read the actual CSV files (the provided files
have no trailing newline; use stdlib `csv`, never naive line-splitting). Demo data anchor (verified): 2 clinics, 4 doctors, 5 treatments,
3 patients, 4 bookings (P001 has B1001 General Checkup 2026-11-05 and B1004 knee consult 2026-11-15), 2
history rows; P001 allergies: Penicillin, Peanuts.

## 8. Frontend (Next.js 14, App Router, Tailwind)

Single page `/` — three panes, no styling ambition beyond clean:

- **PatientCard**: P001 profile + allergy badges (from `/api/patients/{id}/context`).
- **ChatPanel**: message list + input; POST `/api/chat` with `{session_id, message}`; renders
  `booking_created` as a confirmation card and triggers BookingsPanel refresh; shows intent chip per reply.
- **BookingsPanel**: table from `GET /api/bookings?patient_id=P001`; refresh button + auto-refresh on
  `booking_created` (P5 visible live). No polling.
- **SummarizerTab** (bonus): textarea → `POST /api/summarize/transcript` → structured JSON view.

`session_id`: `crypto.randomUUID()` persisted in localStorage. API base: `NEXT_PUBLIC_API_URL` (compose/k8s
route `/api` to backend via one origin; backend still enables CORS for split-origin dev).

## 9. DevOps

**docker-compose.yml** (dev + demo): `postgres:16-alpine` (healthcheck `pg_isready`) → `backend` (depends_on
healthy; entrypoint runs idempotent seed, then uvicorn) → `ai-service` (depends_on backend healthy) →
`frontend` (multi-stage build → `next start`, :3000). Env from root `.env`. Langfuse = cloud keys only.

**k8s/** (demo-grade manifests, `kubectl apply -f k8s/`) — **kept by explicit user requirement** (not just
assignment bonus; the weight-review cut is overridden here): namespace `clinicpilot`; ConfigMap (service
URLs); Secret (DB creds, `OPENAI_API_KEY`, Langfuse keys); Postgres Deployment + PVC (demo-grade;
StatefulSet/cloud DB noted); backend + ai-service + frontend Deployments + ClusterIP Services;
readiness/liveness on `/health` (ai-service probes backend reachability in `/health`); Ingress routing
`/api`→backend, `/`→frontend. No HPA. Last slice — never competes with the graded core for time.

**Config** (`.env.example`): `DATABASE_URL`, `AI_SERVICE_URL`, `BACKEND_URL`, `DEFAULT_PATIENT_ID=P001`,
`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST`
(all optional, P6).

## 10. Test Strategy (regression tests ship with every slice)

- **backend** (pytest, sqlite via env override — models stay portable): booking POST validation (bad FK,
  bad date → 422), seed idempotency (P4), bookings joined read model (P5), catalog contains-match.
- **ai-service** (pytest, scripted fake chat model patched at consumer modules — LedgerMind lesson):
  routing per intent (P1), confirmation "yes"/"no" while draft pending (P1/P2), slots accumulate across turns,
  `create_booking` called once with correct payload only after confirmation (P2/P3 — httpx mocked),
  out-of-scope refusal, missing-slot question rendering.
- **e2e smoke** (optional final slice): `docker compose up` + curl script driving
  ask → recommend → check → book → verify `GET /api/bookings`.

## 11. Implementation Slices (order, each with done-when)

| # | Slice | Done when |
|---|-------|-----------|
| 1 | backend: models + idempotent seed + bookings/catalog/patients endpoints + tests | seeded `GET /api/bookings` returns 4; POST creates a 5th; bad payload → 422 |
| 2 | ai-service: config, LLM factory, state, classifier + general node, `/chat` + `/health`, backend proxy + P7 | fake-LLM test routes all 4 intents; ai down → 503 |
| 3 | booking nodes + slot extraction + confirm gate + `create_booking` tool | multi-turn fake-LLM test books via mocked POST; no-confirmation turn never calls it |
| 4 | qa node + catalog tools + patient context injection (P8) | "knee pain" → answer cites T005+D104; "my next appointment" → B1004 surfaced |
| 5 | frontend: chat + bookings + patient card | manual demo flow completes; new booking appears without manual refresh |
| 6 | Langfuse tracing (P6) + Dockerfiles + compose | traces with session/user/intent visible in Langfuse; `compose up` runs the whole stack seeded |
| 7 | bonus: summarizer endpoint + tab; k8s manifests; README + TECH_DOC | summarize returns 4 fields; `kubectl apply` brings stack up; docs walk setup cold |

Slice 1 is the smallest start; 2–4 build the agent core before any UI; nothing in slices 1–4 blocks on 5–7.
