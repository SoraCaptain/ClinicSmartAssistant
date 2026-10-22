# ai-service image
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/ai

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/srv/ai/.venv/bin:$PATH"

COPY app ./app

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
