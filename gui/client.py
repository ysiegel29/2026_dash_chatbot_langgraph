"""HTTP client for the agent service.

Sync functions are used by Dash background callbacks.
Async variants exist for future use.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
from httpx_sse import connect_sse


def _base() -> str:
    host = os.environ.get("AGENT_HOST", "127.0.0.1")
    port = os.environ.get("AGENT_PORT", "8000")
    return f"http://{host}:{port}"


# ── Thread CRUD ───────────────────────────────────────────────────────────────

def create_thread(
    title: str = "New Chat",
    provider: str = "openai",
    model: str = "gpt-4o",
    temperature: float = 0.7,
) -> dict:
    r = httpx.post(
        f"{_base()}/threads",
        json={"title": title, "provider": provider, "model": model, "temperature": temperature},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def list_threads() -> list[dict]:
    r = httpx.get(f"{_base()}/threads", timeout=10)
    r.raise_for_status()
    return r.json()


def get_thread(thread_id: str) -> dict:
    r = httpx.get(f"{_base()}/threads/{thread_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def delete_thread(thread_id: str) -> None:
    httpx.delete(f"{_base()}/threads/{thread_id}", timeout=10).raise_for_status()


def rename_thread(thread_id: str, title: str) -> None:
    httpx.patch(
        f"{_base()}/threads/{thread_id}",
        json={"title": title},
        timeout=10,
    ).raise_for_status()


def update_thread_model(thread_id: str, provider: str, model: str, temperature: float) -> None:
    httpx.patch(
        f"{_base()}/threads/{thread_id}",
        json={"provider": provider, "model": model, "temperature": temperature},
        timeout=10,
    ).raise_for_status()


# ── Streaming ─────────────────────────────────────────────────────────────────

def stream_message(thread_id: str, content: str) -> Iterator[dict]:
    """Yields SSE event dicts: {"event": str, "data": str}.

    Caller should parse `data` as JSON.
    """
    with httpx.Client(timeout=None) as http_client:
        with connect_sse(
            http_client,
            "POST",
            f"{_base()}/threads/{thread_id}/messages",
            json={"content": content},
        ) as event_source:
            for sse in event_source.iter_sse():
                yield {"event": sse.event or "message", "data": sse.data}


# ── File upload ───────────────────────────────────────────────────────────────

def upload_file(thread_id: str, filename: str, content: bytes, mime: str = "application/octet-stream") -> dict:
    r = httpx.post(
        f"{_base()}/threads/{thread_id}/files",
        files={"file": (filename, content, mime)},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── Artefact download ─────────────────────────────────────────────────────────

def get_artefact_url(thread_id: str, artefact_id: str) -> str:
    return f"{_base()}/threads/{thread_id}/artefacts/{artefact_id}"
