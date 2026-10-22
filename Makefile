# Dev entrypoints (demo-grade). Docker/compose: slice 6.

DATABASE_URL ?= sqlite:////tmp/clinicpilot.db

.PHONY: dev-backend dev-ai dev-frontend test compose-up compose-down

dev-backend:
	cd backend && DATABASE_URL="$(DATABASE_URL)" .venv/bin/uvicorn app.main:app --reload --port 8000

dev-ai:
	cd ai-service && .venv/bin/uvicorn app.main:app --reload --port 8001

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd ai-service && .venv/bin/pytest -q
	cd frontend && npm test

# full stack (postgres + backend + ai + frontend); env from root .env
compose-up:
	docker compose up --build -d

compose-down:
	docker compose down -v
