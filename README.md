# ClinicPilot AI

An end-to-end clinic assistant demo. A patient (fixed demo identity **P001, John Doe**) chats with an AI assistant that

- answers clinic / doctor / treatment questions grounded in the clinic catalog (RAG over structured retrieval, answers cite row IDs),
- reads the patient's existing bookings,
- completes a new booking through multi-turn slot filling and an explicit confirmation gate — the agent triggers the REST API itself, and the new booking appears in the UI immediately,
- (bonus) summarizes a doctor–patient transcript into four structured clinical fields.

Three services: **frontend** (Next.js 14) → **backend** (FastAPI + PostgreSQL, the BFF) → **ai-service** (FastAPI + LangGraph). The backend proxies `POST /api/chat` to the AI engine; the agent's tools call backend REST endpoints over httpx, so the AI engine never touches the database. Langfuse traces every chat turn (optional).

Full design and as-built documentation: [TECH_DOC.md](TECH_DOC.md).

## Quickstart (docker compose)

Prereqs: Docker; an API key for any OpenAI-compatible provider.

```bash
cp .env.example .env          # then edit: set OPENAI_API_KEY (and provider settings if not OpenAI)
docker compose up --build -d  # or: make compose-up
open http://localhost:3000
```

The stack boots postgres (healthchecked) → backend (seeds demo data on start, idempotent) → ai-service → frontend.

> `LLM_MODEL` must be a **non-thinking** model if your provider has thinking modes (e.g. DeepSeek: use `deepseek-chat`, not a reasoning model) — structured-output calls force `tool_choice`, which thinking endpoints reject.

## Demo script

1. Chat: *"My knee hurts when I climb stairs — what could help?"* → grounded answer citing catalog rows (e.g. T005, D104).
2. Chat: *"When is my next appointment?"* → surfaces the upcoming knee consult (B1004, 2026-11-15).
3. Chat: *"Book a joint & pain consultation with Dr. Wilson on Nov 21 at 9:30"* → assistant renders a summary and asks to confirm → reply *"yes"* → confirmation card in chat, and the booking shows up in **My bookings** without a manual refresh.
4. **Summarizer** tab (right pane): paste any doctor–patient transcript → chief complaint, diagnosis, medication, doctor instructions.

## Local development

```bash
make dev-backend    # uvicorn :8000 (sqlite by default via DATABASE_URL)
make dev-ai         # uvicorn :8001 (reads OPENAI_* from root .env)
make dev-frontend   # next dev :3000
make test           # backend + ai-service (pytest) and frontend (vitest)
```

Python services use `uv` (`uv sync` inside `backend/` / `ai-service/`); the frontend uses `npm install`.

## Configuration (root `.env`)

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | backend | sqlite for dev, postgres in compose/k8s |
| `AI_SERVICE_URL` | backend | where the `/api/chat` proxy forwards |
| `BACKEND_URL` | ai-service | base URL of the REST tools |
| `DEFAULT_PATIENT_ID` | ai-service | fallback patient (`P001`) when `/chat` carries none |
| `OPENAI_API_KEY` | ai-service | **required** for any chat/summarize call |
| `OPENAI_BASE_URL` | ai-service | any OpenAI-compatible provider |
| `LLM_MODEL` | ai-service | one model for everything; non-thinking (see note above) |
| `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` | ai-service | optional; absent keys → tracing off |

## Kubernetes (demo-grade)

```bash
# 1. set secrets (at minimum OPENAI_API_KEY; non-OpenAI providers must also
#    set OPENAI_BASE_URL / LLM_MODEL — non-thinking — in k8s/01-config.yaml)
$EDITOR k8s/02-secret.yaml
# 2. build the three images (frontend bakes the ingress origin into its bundle)
make k8s-build                    # K8S_FRONTEND_ORIGIN defaults to http://clinicpilot.local
# 3. make the images visible to your cluster node, e.g.
minikube image load clinicpilot/backend:latest clinicpilot/ai:latest clinicpilot/frontend:latest
#    or: kind load docker-image clinicpilot/backend:latest clinicpilot/ai:latest clinicpilot/frontend:latest
# 4. apply (needs an ingress controller, e.g. `minikube addons enable ingress`)
kubectl apply -f k8s/             # or: make k8s-apply
# 5. route the ingress host
echo "$(minikube ip) clinicpilot.local" | sudo tee -a /etc/hosts
kubectl get ingress -n clinicpilot
```

If you use a different host, rebuild the frontend with `K8S_FRONTEND_ORIGIN=http://<host> make k8s-build` — `NEXT_PUBLIC_API_URL` is inlined into the client bundle at build time.

## API summary

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | backend liveness: `{status, db}` |
| `POST /api/chat` | chat proxy → ai-service (`{session_id, message, patient_id?}` → `{reply, intent, booking_created?, session_id}`) |
| `GET /api/bookings?patient_id=` | joined read model for the UI |
| `POST /api/bookings` | create booking (FK + format validation, no conflict check) → 201 |
| `GET /api/doctors?specialty=` `GET /api/treatments?search=` `GET /api/clinics` | catalog reads (contains-match) used by the agent tools |
| `GET /api/patients/{id}/context` | profile + allergies + history + upcoming bookings |
| `POST /api/summarize/transcript` | bonus: transcript → `{chief_complaint, diagnosis, medication, doctor_instructions}` |

ai-service (internal): `POST /chat`, `POST /summarize`, `GET /health` (reports backend reachability — k8s readiness), `GET /livez` (process-only liveness). Chat proxy returns **503** when the ai-service is unreachable (no canned fallback), **502** on upstream errors.

## Project layout

```
ai-service/   LangGraph agent (classifier → qa / bookings / booking-flow / general), tools over REST, Langfuse
backend/      FastAPI + SQLAlchemy models, routers, services, idempotent CSV seed
frontend/     Next.js 14 App Router + Tailwind: patient card, chat, bookings/summarizer tabs
mock-data/    provided demo CSVs (seed source)
k8s/          namespace, config, secret, postgres, backend, ai, frontend, ingress
docker-compose.yml / Makefile / .env.example
```

## Demo-grade simplifications (by assignment scope)

Single preloaded patient, no auth/RBAC, no schedule-conflict validation, in-memory conversation checkpointer (single ai-service replica), k8s postgres is a plain Deployment + PVC (no HA), no streaming responses. Details and upgrade paths: [TECH_DOC.md](TECH_DOC.md).
