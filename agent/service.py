"""FastAPI agent service.

Endpoints
─────────
POST   /threads                          create a new thread
GET    /threads                          list all threads
GET    /threads/{id}                     get thread metadata + messages
DELETE /threads/{id}                     delete thread
PATCH  /threads/{id}                     update thread title / model config
POST   /threads/{id}/messages            send a message → SSE stream
GET    /threads/{id}/artefacts/{name}    download an artefact by name
POST   /threads/{id}/files               upload a file into the virtual FS
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .graph import build_graph
from .tools.mcp_tools import close_mcp_client, init_mcp_tools

logger = logging.getLogger(__name__)

# ── DB helpers ────────────────────────────────────────────────────────────────

def _db_path() -> str:
    # Separate file from the LangGraph checkpoint DB to avoid locking contention
    default = os.environ.get("DB_PATH", "data/checkpoints.db")
    return os.environ.get("METADATA_DB_PATH", default.replace("checkpoints", "metadata"))


@contextmanager
def _db():
    path = _db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")   # allow concurrent readers
    conn.execute("PRAGMA synchronous=NORMAL") # faster writes, still safe
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL DEFAULT 'New Chat',
                provider    TEXT NOT NULL DEFAULT 'openai',
                model       TEXT NOT NULL DEFAULT 'gpt-4o',
                temperature REAL NOT NULL DEFAULT 0.7,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artefacts (
                id          TEXT PRIMARY KEY,
                thread_id   TEXT NOT NULL,
                name        TEXT NOT NULL,
                type        TEXT NOT NULL,
                content     TEXT NOT NULL,
                mime_type   TEXT NOT NULL DEFAULT 'application/octet-stream',
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── App lifecycle ─────────────────────────────────────────────────────────────

_checkpointer = None
_default_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _checkpointer, _default_graph
    cp_path = os.environ.get("DB_PATH", "data/checkpoints.db")
    os.makedirs(os.path.dirname(os.path.abspath(cp_path)), exist_ok=True)
    # Enable WAL mode on checkpoint DB to prevent "database is locked" under concurrency
    _init = sqlite3.connect(cp_path, check_same_thread=False)
    _init.execute("PRAGMA journal_mode=WAL")
    _init.execute("PRAGMA synchronous=NORMAL")
    _init.close()
    async with AsyncSqliteSaver.from_conn_string(cp_path) as cp:
        _checkpointer = cp
        await init_mcp_tools()
        _default_graph = build_graph(_checkpointer)
        logger.info("Agent graph ready (AsyncSqliteSaver).")
        yield
        await close_mcp_client()
    _checkpointer = None


app = FastAPI(title="Agent Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ThreadCreate(BaseModel):
    title: str = "New Chat"
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7


class ThreadPatch(BaseModel):
    title: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None


class MessageRequest(BaseModel):
    content: str


# ── Thread endpoints ──────────────────────────────────────────────────────────

@app.post("/threads", status_code=201)
def create_thread(req: ThreadCreate):
    tid = str(uuid.uuid4())
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?)",
            (tid, req.title, req.provider, req.model, req.temperature, now, now),
        )
    return {"id": tid, "title": req.title, "provider": req.provider,
            "model": req.model, "temperature": req.temperature,
            "created_at": now, "updated_at": now}


@app.get("/threads")
def list_threads():
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM threads ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    with _db() as conn:
        row = conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Thread not found")

    # Fetch message history from checkpointer
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await _checkpointer.aget(config) if _checkpointer else None
    messages = []
    if snapshot:
        for msg in snapshot.get("channel_values", {}).get("messages", []):
            role = getattr(msg, "type", "unknown")
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            messages.append({"id": getattr(msg, "id", ""), "role": role, "content": content})

    # Fetch artefacts
    with _db() as conn:
        arts = conn.execute(
            "SELECT * FROM artefacts WHERE thread_id=? ORDER BY created_at",
            (thread_id,),
        ).fetchall()

    return {**dict(row), "messages": messages, "artefacts": [dict(a) for a in arts]}


@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    with _db() as conn:
        conn.execute("DELETE FROM threads WHERE id=?", (thread_id,))
        conn.execute("DELETE FROM artefacts WHERE thread_id=?", (thread_id,))
    return {"ok": True}


@app.patch("/threads/{thread_id}")
def patch_thread(thread_id: str, req: ThreadPatch):
    fields, vals = [], []
    if req.title is not None:
        fields.append("title=?"); vals.append(req.title)
    if req.provider is not None:
        fields.append("provider=?"); vals.append(req.provider)
    if req.model is not None:
        fields.append("model=?"); vals.append(req.model)
    if req.temperature is not None:
        fields.append("temperature=?"); vals.append(req.temperature)
    if not fields:
        return {"ok": True}
    fields.append("updated_at=?"); vals.append(_now())
    vals.append(thread_id)
    with _db() as conn:
        conn.execute(f"UPDATE threads SET {', '.join(fields)} WHERE id=?", vals)
    return {"ok": True}


# ── Messaging / streaming ─────────────────────────────────────────────────────

@app.post("/threads/{thread_id}/messages")
async def send_message(thread_id: str, req: MessageRequest):
    with _db() as conn:
        row = conn.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Thread not found")

    thread = dict(row)
    logger.info("send_message: thread=%s provider=%s model=%s msg=%.80s",
                thread_id, thread["provider"], thread["model"], req.content)

    # Rebuild graph if the thread uses a non-default model config
    graph = build_graph(
        _checkpointer,
        provider=thread["provider"],
        model=thread["model"],
        temperature=thread["temperature"],
    )

    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        token_count = 0
        try:
            async for mode, chunk in graph.astream(
                {"messages": [HumanMessage(content=req.content)]},
                config=config,
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    # chunk is (message_chunk, metadata)
                    msg_chunk, _ = chunk

                    # Only stream AI response tokens — skip ToolMessage, HumanMessage, etc.
                    if msg_chunk.type not in ("ai", "AIMessageChunk"):
                        continue

                    raw = msg_chunk.content
                    # Normalise: Anthropic streams content as list of blocks
                    if isinstance(raw, list):
                        text = "".join(
                            b.get("text", "") if isinstance(b, dict) else str(b)
                            for b in raw
                        )
                    elif isinstance(raw, str):
                        text = raw
                    else:
                        text = str(raw) if raw else ""

                    if text:
                        token_count += 1
                        if token_count == 1:
                            logger.info("  → first AI token received")
                        yield {
                            "event": "token",
                            "data": json.dumps({"content": text}),
                        }

                elif mode == "updates":
                    # chunk is {node_name: state_delta}
                    for _node, delta in chunk.items():
                        # Emit tool call markers
                        if hasattr(delta, "get"):
                            for msg in delta.get("messages", []):
                                # ToolMessage signals a completed tool call
                                if getattr(msg, "type", "") == "tool":
                                    raw_out = msg.content
                                    if isinstance(raw_out, str):
                                        output = raw_out
                                    elif isinstance(raw_out, list):
                                        # MCP / Anthropic return list of content blocks
                                        output = "\n".join(
                                            b.get("text", str(b)) if isinstance(b, dict) else str(b)
                                            for b in raw_out
                                        )
                                    else:
                                        output = str(raw_out)
                                    yield {
                                        "event": "tool_end",
                                        "data": json.dumps({
                                            "tool": getattr(msg, "name", ""),
                                            "output": output,
                                        }),
                                    }
                            # Emit new artefacts
                            for art in delta.get("artefacts", []):
                                # Persist to DB
                                with _db() as conn:
                                    conn.execute(
                                        "INSERT OR IGNORE INTO artefacts "
                                        "(id, thread_id, name, type, content, mime_type, created_at) "
                                        "VALUES (?,?,?,?,?,?,?)",
                                        (
                                            art["id"], thread_id, art["name"],
                                            art["type"], art["content"],
                                            art.get("mime_type", "application/octet-stream"),
                                            _now(),
                                        ),
                                    )
                                yield {
                                    "event": "artefact",
                                    "data": json.dumps({
                                        "id": art["id"],
                                        "name": art["name"],
                                        "type": art["type"],
                                        "content": art["content"],
                                        "mime_type": art.get("mime_type", ""),
                                    }),
                                }

            # Update thread timestamp
            with _db() as conn:
                conn.execute(
                    "UPDATE threads SET updated_at=? WHERE id=?",
                    (_now(), thread_id),
                )

            logger.info("  → stream done (%d tokens)", token_count)
            yield {"event": "done", "data": json.dumps({"status": "ok"})}

        except Exception as exc:
            logger.exception("Stream error for thread %s", thread_id)
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}

    return EventSourceResponse(event_generator())


# ── File upload ───────────────────────────────────────────────────────────────

@app.post("/threads/{thread_id}/files")
async def upload_file(thread_id: str, file: UploadFile = File(...)):
    with _db() as conn:
        row = conn.execute("SELECT id FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Thread not found")

    content = await file.read()
    b64 = base64.b64encode(content).decode()

    # Inject into agent state via a synthetic checkpoint update
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await _checkpointer.aget(config) if _checkpointer else None

    if snapshot:
        vf = snapshot.get("channel_values", {}).get("virtual_files", {})
        vf[file.filename] = b64
        # Write updated virtual_files back via a dummy graph invoke is complex;
        # instead, we store the file in a side-channel the graph reads on next invoke.
        # For simplicity, we record it in the artefacts table as type="file".
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artefacts VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), thread_id, file.filename, "file",
                 b64, file.content_type or "application/octet-stream", _now()),
            )

    return {"filename": file.filename, "size": len(content)}


# ── Artefact download ─────────────────────────────────────────────────────────

@app.get("/threads/{thread_id}/artefacts/{artefact_id}")
def download_artefact(thread_id: str, artefact_id: str):
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM artefacts WHERE id=? AND thread_id=?",
            (artefact_id, thread_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Artefact not found")

    art = dict(row)
    if art["type"] in ("html", "text", "plotly", "table"):
        body = art["content"].encode()
    else:
        try:
            body = base64.b64decode(art["content"])
        except Exception:
            # LLM may have stored plain text instead of base64
            body = art["content"].encode()

    return Response(
        content=body,
        media_type=art["mime_type"],
        headers={"Content-Disposition": f'attachment; filename="{art["name"]}"'},
    )


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    import sys
    import uvicorn

    # Ensure project root is importable regardless of how the entry point was invoked
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    host = os.environ.get("AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("AGENT_PORT", "8000"))
    uvicorn.run(
        "agent.service:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=[os.path.join(root, "agent")],  # never watch .venv
    )


if __name__ == "__main__":
    main()
