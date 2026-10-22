# backend image — build context is the REPO ROOT (mock-data lives there;
# seed_service resolves parents[3]/mock-data, so /srv/mock-data matches)
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/srv/backend/.venv/bin:$PATH"

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY mock-data /srv/mock-data

EXPOSE 8000
# DESIGN §9: idempotent seed (P4) before serving; lifespan re-seeds harmlessly
CMD ["sh", "-c", "python -m scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
