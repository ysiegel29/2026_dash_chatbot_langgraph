"""All Dash callbacks, registered via register_callbacks(app, manager)."""
from __future__ import annotations

import json
import logging
import uuid

from dash import ALL, Input, Output, State, no_update, set_props
from dash.exceptions import PreventUpdate

log = logging.getLogger("gui.callbacks")

from . import client as agent_client
from . import ids
from .components import message_row, streaming_bubble, welcome_screen
from .models_meta import PROVIDER_MODELS


def register_callbacks(app, background_callback_manager):
    """Call once after Dash() is instantiated."""

    # ── Theme toggle ──────────────────────────────────────────────────────────

    app.clientside_callback(
        """
        function(theme) {
            document.documentElement.setAttribute('data-theme', theme || 'light');
            return theme === 'dark' ? '☀' : '🌙';
        }
        """,
        Output(ids.THEME_TOGGLE, "children"),
        Input(ids.THEME_STORE, "data"),
    )

    @app.callback(
        Output(ids.THEME_STORE, "data"),
        Input(ids.THEME_TOGGLE, "n_clicks"),
        State(ids.THEME_STORE, "data"),
        prevent_initial_call=True,
    )
    def toggle_theme(n, current):
        new = "dark" if (current or "light") == "light" else "light"
        log.info("toggle_theme → %s", new)
        return new

    # ── Provider → model list ─────────────────────────────────────────────────

    @app.callback(
        Output(ids.MODEL_SELECT, "options"),
        Output(ids.MODEL_SELECT, "value"),
        Input(ids.PROVIDER_SELECT, "value"),
    )
    def update_model_list(provider):
        models = PROVIDER_MODELS.get(provider or "openai", [])
        opts = [{"label": m, "value": m} for m in models]
        return opts, (models[0] if models else None)

    # ── Bootstrap thread list on page load ────────────────────────────────────

    @app.callback(
        Output(ids.THREADS_DATA_STORE, "data"),
        Output(ids.THREAD_ID_STORE, "data"),
        Input(ids.INIT_INTERVAL, "n_intervals"),
    )
    def load_threads_on_start(_):
        log.info("load_threads_on_start fired")
        try:
            threads = agent_client.list_threads()
            log.info("  → %d threads returned", len(threads))
        except Exception as e:
            log.warning("  → agent unreachable: %s", e)
            threads = []
        active = threads[0]["id"] if threads else None
        return threads, active

    # ── Thread list rendering ─────────────────────────────────────────────────

    @app.callback(
        Output(ids.THREAD_LIST, "children"),
        Input(ids.THREADS_DATA_STORE, "data"),
        State(ids.THREAD_ID_STORE, "data"),
    )
    def render_thread_list(threads, active_id):
        log.info("render_thread_list: %d threads, active=%s", len(threads or []), active_id)
        from dash import html
        if not threads:
            return html.Div(
                "No threads yet.",
                style={"padding": ".75rem", "color": "var(--text-secondary)", "fontSize": ".8rem"},
            )
        items = []
        for t in threads:
            is_active = t["id"] == active_id
            items.append(
                html.Div(
                    [
                        html.Span(
                            t.get("title", "Untitled")[:40],
                            style={"flex": "1", "overflow": "hidden", "textOverflow": "ellipsis"},
                        ),
                        html.Button(
                            "✕",
                            id={"type": "delete-thread-btn", "index": t["id"]},
                            n_clicks=0,
                            className="delete-btn",
                            title="Delete thread",
                        ),
                    ],
                    id={"type": "thread-item", "index": t["id"]},
                    className=f"thread-item {'active' if is_active else ''}",
                    n_clicks=0,
                )
            )
        return items

    # ── Switch thread ─────────────────────────────────────────────────────────

    @app.callback(
        Output(ids.THREAD_ID_STORE, "data", allow_duplicate=True),
        Output(ids.MESSAGES_STORE, "data", allow_duplicate=True),
        Input({"type": "thread-item", "index": ALL}, "n_clicks"),
        State({"type": "thread-item", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def switch_thread(n_clicks_list, id_list):
        from dash import ctx
        if not ctx.triggered_id:
            raise PreventUpdate
        tid = ctx.triggered_id["index"]
        try:
            thread = agent_client.get_thread(tid)
        except Exception:
            raise PreventUpdate
        messages = []
        for msg in thread.get("messages", []):
            role = msg.get("role", "")
            if role == "tool":
                continue
            messages.append({
                "id": msg.get("id", str(uuid.uuid4())),
                "role": "user" if role == "human" else "assistant",
                "blocks": [{"type": "text", "content": msg.get("content", "")}],
                "tool_calls": [],
            })
        return tid, messages

    # ── Delete thread ─────────────────────────────────────────────────────────

    @app.callback(
        Output(ids.THREADS_DATA_STORE, "data", allow_duplicate=True),
        Output(ids.THREAD_ID_STORE, "data", allow_duplicate=True),
        Output(ids.MESSAGES_STORE, "data", allow_duplicate=True),
        Input({"type": "delete-thread-btn", "index": ALL}, "n_clicks"),
        State({"type": "delete-thread-btn", "index": ALL}, "id"),
        State(ids.THREAD_ID_STORE, "data"),
        prevent_initial_call=True,
    )
    def delete_thread(n_clicks_list, id_list, active_id):
        if not any(n_clicks_list):
            raise PreventUpdate
        from dash import ctx
        tid = ctx.triggered_id["index"]
        try:
            agent_client.delete_thread(tid)
        except Exception:
            pass
        threads = agent_client.list_threads()
        new_active = active_id if active_id != tid else (threads[0]["id"] if threads else None)
        return threads, new_active, []

    # ── New chat ──────────────────────────────────────────────────────────────

    @app.callback(
        Output(ids.THREAD_ID_STORE, "data", allow_duplicate=True),
        Output(ids.THREADS_DATA_STORE, "data", allow_duplicate=True),
        Output(ids.MESSAGES_STORE, "data", allow_duplicate=True),
        Input(ids.NEW_CHAT_BTN, "n_clicks"),
        State(ids.PROVIDER_SELECT, "value"),
        State(ids.MODEL_SELECT, "value"),
        prevent_initial_call=True,
    )
    def new_chat(n, provider, model):
        if not n:
            raise PreventUpdate
        log.info("new_chat: provider=%s model=%s", provider, model)
        t = agent_client.create_thread(provider=provider or "openai", model=model or "gpt-4o")
        threads = agent_client.list_threads()
        log.info("  → new thread %s, total %d", t["id"], len(threads))
        return t["id"], threads, []

    # ── Messages area render ──────────────────────────────────────────────────

    @app.callback(
        Output(ids.MESSAGES_SCROLL, "children"),
        Input(ids.MESSAGES_STORE, "data"),
        State(ids.THREAD_ID_STORE, "data"),
    )
    def render_messages(messages, thread_id):
        log.info("render_messages: %d messages, thread=%s", len(messages or []), thread_id)
        from dash import html
        stream_div = html.Div(id=ids.STREAM_MESSAGE)
        if not messages:
            return [welcome_screen(), stream_div]
        rows = [message_row(m, thread_id or "") for m in messages]
        rows.append(stream_div)
        return rows

    # ── Example prompts → fill composer ──────────────────────────────────────

    @app.callback(
        Output(ids.COMPOSER, "value"),
        Input({"type": "example-prompt", "index": ALL}, "n_clicks"),
        State({"type": "example-prompt", "index": ALL}, "children"),
        prevent_initial_call=True,
    )
    def fill_from_example(n_clicks_list, texts):
        if not any(n_clicks_list):
            raise PreventUpdate
        idx = next(i for i, n in enumerate(n_clicks_list) if n)
        raw = str(texts[idx])
        text = raw.split("  ", 1)[-1] if "  " in raw else raw
        return text

    # ── File upload ───────────────────────────────────────────────────────────

    @app.callback(
        Output(ids.UPLOAD_STORE, "data"),
        Input(ids.UPLOAD, "contents"),
        State(ids.UPLOAD, "filename"),
        State(ids.THREAD_ID_STORE, "data"),
        prevent_initial_call=True,
    )
    def handle_upload(contents, filename, thread_id):
        if not contents or not thread_id:
            raise PreventUpdate
        import base64
        # contents is "data:<mime>;base64,<data>"
        header, b64 = contents.split(",", 1)
        mime = header.split(":")[1].split(";")[0] if ":" in header else "application/octet-stream"
        data = base64.b64decode(b64)
        try:
            agent_client.upload_file(thread_id, filename, data, mime)
        except Exception as e:
            return {"error": str(e), "filename": filename}
        return {"filename": filename, "size": len(data)}

    # ── Model change on active thread ─────────────────────────────────────────

    @app.callback(
        Output(ids.THREADS_DATA_STORE, "data", allow_duplicate=True),
        Input(ids.PROVIDER_SELECT, "value"),
        Input(ids.MODEL_SELECT, "value"),
        State(ids.THREAD_ID_STORE, "data"),
        prevent_initial_call=True,
    )
    def push_model_to_thread(provider, model, thread_id):
        if not thread_id or not provider or not model:
            raise PreventUpdate
        log.info("push_model_to_thread: thread=%s provider=%s model=%s", thread_id, provider, model)
        try:
            agent_client.update_thread_model(thread_id, provider, model, 0.7)
        except Exception as e:
            log.warning("  → update_thread_model failed: %s", e)
        raise PreventUpdate  # no need to refresh the list; model update is local

    # ── Send message (streaming background callback) ──────────────────────────

    @app.callback(
        Output(ids.MESSAGES_STORE, "data", allow_duplicate=True),
        Input(ids.SEND_BTN, "n_clicks"),
        State(ids.THREAD_ID_STORE, "data"),
        State(ids.COMPOSER, "value"),
        State(ids.MESSAGES_STORE, "data"),
        background=True,
        manager=background_callback_manager,
        running=[
            (Output(ids.SEND_BTN, "disabled"), True, False),
            (Output(ids.COMPOSER, "disabled"), True, False),
        ],
        prevent_initial_call=True,
    )
    def handle_send(n_clicks, thread_id, message, existing_messages):
        if not n_clicks or not message:
            raise PreventUpdate

        message = message.strip()
        if not message:
            raise PreventUpdate

        # Auto-create a thread if none is active yet
        if not thread_id:
            try:
                t = agent_client.create_thread()
                thread_id = t["id"]
                set_props(ids.THREAD_ID_STORE, {"data": thread_id})
                threads = agent_client.list_threads()
                set_props(ids.THREADS_DATA_STORE, {"data": threads})
                log.info("handle_send: auto-created thread %s", thread_id)
            except Exception as e:
                log.error("handle_send: could not create thread: %s", e)
                raise PreventUpdate

        log.info("handle_send: thread=%s msg=%.60s", thread_id, message)
        user_msg = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "blocks": [{"type": "text", "content": message}],
            "tool_calls": [],
        }
        messages = list(existing_messages or []) + [user_msg]
        set_props(ids.MESSAGES_STORE, {"data": messages})
        set_props(ids.COMPOSER, {"value": ""})

        streaming_blocks: list[dict] = []
        tool_calls_acc: list[dict] = []

        def _push():
            set_props(ids.STREAM_MESSAGE, {
                "children": streaming_bubble(streaming_blocks).children,
            })

        try:
            for event in agent_client.stream_message(thread_id, message):
                etype = event.get("event", "message")
                try:
                    data = json.loads(event.get("data", "{}"))
                except json.JSONDecodeError:
                    data = {"content": event.get("data", "")}

                if etype == "token":
                    raw = data.get("content", "")
                    # Normalise to str (server should already do this, belt-and-suspenders)
                    if isinstance(raw, list):
                        content = "".join(
                            c.get("text", str(c)) if isinstance(c, dict) else str(c)
                            for c in raw
                        )
                    else:
                        content = str(raw) if raw else ""

                    if content:
                        if streaming_blocks and streaming_blocks[-1]["type"] == "text":
                            streaming_blocks[-1]["content"] += content
                        else:
                            streaming_blocks.append({"type": "text", "content": content})
                        _push()

                elif etype == "tool_end":
                    tool_calls_acc.append({
                        "tool": data.get("tool", ""),
                        "output": data.get("output", ""),
                    })

                elif etype == "artefact":
                    atype = data.get("type", "file")
                    # **data first, then "type" — our normalised type must win
                    streaming_blocks.append({
                        **data,
                        "type": atype if atype in ("plotly", "table", "html", "image") else "artefact",
                    })
                    _push()

                elif etype == "done":
                    break

                elif etype == "error":
                    streaming_blocks.append({
                        "type": "text",
                        "content": f"**Error:** {data.get('error', 'Unknown error')}",
                    })
                    _push()
                    break

        except Exception as exc:
            streaming_blocks.append({"type": "text", "content": f"**Connection error:** {exc}"})
            _push()

        assistant_msg = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "blocks": streaming_blocks,
            "tool_calls": tool_calls_acc,
        }
        set_props(ids.STREAM_MESSAGE, {"children": []})
        return messages + [assistant_msg]
