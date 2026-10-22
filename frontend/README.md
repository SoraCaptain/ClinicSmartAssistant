# ClinicPilot AI — frontend

Next.js 14 (App Router) + Tailwind. Single page with three panes: patient card,
chat, bookings. No polling — the bookings table auto-refreshes when the chat
completes a booking (`booking_created` in the `/api/chat` response).

## Run

```bash
npm install
npm run dev          # http://localhost:3000
```

Requires the backend on `:8000` and the ai-service on `:8001` (see root
`Makefile`: `make dev-backend`, `make dev-ai`).

## Configuration

- `NEXT_PUBLIC_API_URL` — backend base URL. Default `http://localhost:8000`
  (split-origin dev; backend has CORS enabled). For same-origin deployments
  (compose/k8s behind one ingress) set it to an empty string at build time.

## Tests

```bash
npm test             # vitest: api client, session persistence, components
npm run build        # typecheck + production build
```
