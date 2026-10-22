# Dev entrypoints (demo-grade). Docker/compose: slice 6.

DATABASE_URL ?= sqlite:////tmp/clinicpilot.db

# k8s image builds: the frontend API base is inlined at build time, so it must
# match the ingress host (README §k8s).
K8S_FRONTEND_ORIGIN ?= http://clinicpilot.local

.PHONY: dev-backend dev-ai dev-frontend test compose-up compose-down k8s-build k8s-apply k8s-delete

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

# --- k8s (demo-grade manifests; images must be visible to the cluster node:
# minikube: `minikube image load clinicpilot/backend:latest ...`, kind: `kind load docker-image ...`) ---
k8s-build:
	docker build -f backend/Dockerfile -t clinicpilot/backend:latest .
	docker build -t clinicpilot/ai:latest ./ai-service
	docker build --build-arg NEXT_PUBLIC_API_URL=$(K8S_FRONTEND_ORIGIN) -t clinicpilot/frontend:latest ./frontend

k8s-apply:
	kubectl apply -f k8s/

k8s-delete:
	kubectl delete namespace clinicpilot --ignore-not-found
