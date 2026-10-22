"""HTTP plumbing for the REST tools (P3: ai-service reaches the backend only over
HTTP). Errors are re-raised as readable RuntimeError so nodes/UX can surface them
(fail loud, no silent fallbacks). Tests swap `_transport` for an httpx.MockTransport."""

import httpx

from app.core.config import settings

_transport: httpx.BaseTransport | None = None  # test hook; None = real network


def _get(path: str, params: dict | None = None) -> list | dict:
    try:
        with httpx.Client(base_url=settings.backend_url, timeout=10.0, transport=_transport) as client:
            resp = client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"backend GET {path} failed: {e.response.status_code} {e.response.text[:200]}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"backend unreachable at {settings.backend_url}: {e}") from e


def _post(path: str, payload: dict) -> dict:
    try:
        with httpx.Client(base_url=settings.backend_url, timeout=10.0, transport=_transport) as client:
            resp = client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"backend POST {path} failed: {e.response.status_code} {e.response.text[:200]}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"backend unreachable at {settings.backend_url}: {e}") from e
