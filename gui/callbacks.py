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

    # Re-theme every rendered Plotly chart whenever the theme toggles or new
    # messages (which may contain charts) are rendered. Backgrounds are already
    # transparent (set in components._apply_theme_defaults); here we only patch
    # the colours that must follow the dark/light CSS variables: font + gridlines.
    app.clientside_callback(
        """
        function(theme, _children) {
            if (!window.Plotly) return window.dash_clientside.no_update;
            // Defer one tick so freshly-rendered graphs are mounted in the DOM.
            setTimeout(function () {
                var dark = (theme === 'dark');
                // Text: dark grey on white theme, very light grey on dark theme.
                var text = dark ? '#d0d0d0' : '#444444';
                // Gridlines: dark grey on dark theme, subtle light grey on white.
                var grid = dark ? '#444444' : '#e0e0e0';
                // Lighter greens in dark mode so lines stay visible on the dark bg.
                var colorway = (theme === 'dark')
                    ? ['#5cc9b8', '#7ad6c8', '#43b3a0', '#9ae3d8', '#2e9a89']
                    : ['#039c88', '#43b3a0', '#026e60', '#5cc9b8', '#01786b'];
                document.querySelectorAll('.js-plotly-plot').forEach(function (gd) {
                    window.Plotly.relayout(gd, {
                        'paper_bgcolor': 'rgba(0,0,0,0)',
                        'plot_bgcolor': 'rgba(0,0,0,0)',
                        'font.color': text,
                        'xaxis.gridcolor': grid, 'yaxis.gridcolor': grid,
                        'xaxis.zerolinecolor': grid, 'yaxis.zerolinecolor': grid,
                        'xaxis.linecolor': grid, 'yaxis.linecolor': grid,
                        'legend.font.color': text,
                        'colorway': colorway,
                    });
                });
            }, 50);
            return window.dash_clientside.no_update;
        }
        """,
        Output(ids.GRAPH_THEME_DUMMY, "data"),
        Input(ids.THEME_STORE, "data"),
        Input(ids.MESSAGES_SCROLL, "children"),
    )

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
        Input(ids.THREAD_ID_STORE, "data"),
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
        # When the thread list is rebuilt (e.g. after generate_title), the new
        # thread-item components fire this pattern-matching callback with n_clicks=0.
        # Only react to a genuine click, otherwise we'd overwrite MESSAGES_STORE with
        # the server's text-only history and wipe freshly-rendered charts/tables.
        clicked = next((n for n, cid in zip(n_clicks_list, id_list) if cid.get("index") == tid), 0)
        if not clicked:
            raise PreventUpdate
        try:
            thread = agent_client.get_thread(tid)
        except Exception:
            raise PreventUpdate
        messages = []
        pending_tools: list = []

        def _flush_tools():
            # Tool outputs sit between the AI message that invoked them and the
            # final AI reply. Attach them to the turn's last assistant message so
            # the tool rows reappear under it, matching the live-stream rendering.
            if not pending_tools:
                return
            last = next((m for m in reversed(messages) if m["role"] == "assistant"), None)
            if last is not None:
                last["tool_calls"].extend(pending_tools)
            pending_tools.clear()

        for msg in thread.get("messages", []):
            role = msg.get("role", "")
            if role == "tool":
                pending_tools.append({"tool": msg.get("name", ""), "output": msg.get("content", "")})
                continue
            if role == "human":
                _flush_tools()  # close out the previous turn before the new one starts
            messages.append({
                "id": msg.get("id", str(uuid.uuid4())),
                "role": "user" if role == "human" else "assistant",
                "blocks": [{"type": "text", "content": msg.get("content", "")}],
                "tool_calls": [],
            })
        _flush_tools()

        # Re-attach persisted artefacts (charts/tables/images/files) so reopening a
        # thread shows them again — the checkpointer only stores text; artefacts live
        # in their own table and come back via thread["artefacts"], tagged with the
        # assistant message that produced them so each lands under the right turn.
        def _art_block(a: dict) -> dict:
            atype = a.get("type", "file")
            if atype in ("plotly", "table", "html"):
                return {"type": atype, "content": a.get("content", ""),
                        "id": a["id"], "name": a.get("name", "")}
            if atype == "image":
                content = a.get("content", "")
                src = content if content.startswith("data:") else \
                    f"data:{a.get('mime_type', 'image/png')};base64,{content}"
                return {"type": "image", "content": src}
            return {"type": "artefact", "id": a["id"],
                    "name": a.get("name", ""), "mime_type": a.get("mime_type", "")}

        by_msg: dict = {}
        unassigned: list = []
        for a in thread.get("artefacts", []):
            mid = a.get("message_id")
            (by_msg.setdefault(mid, []) if mid else unassigned).append(_art_block(a))

        for m in messages:
            if m["role"] == "assistant" and m["id"] in by_msg:
                m["blocks"].extend(by_msg[m["id"]])

        # Older artefacts (created before per-message tagging) have no message_id —
        # fall back to attaching them to the final assistant message.
        if unassigned:
            last_assistant = next((m for m in reversed(messages) if m["role"] == "assistant"), None)
            if last_assistant is not None:
                last_assistant["blocks"].extend(unassigned)
            else:
                messages.append({"id": str(uuid.uuid4()), "role": "assistant",
                                 "blocks": unassigned, "tool_calls": []})

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
        prevent_initial_call=True,
    )
    def new_chat(n):
        if not n:
            raise PreventUpdate
        log.info("new_chat")
        t = agent_client.create_thread()
        threads = agent_client.list_threads()
        log.info("  → new thread %s, total %d", t["id"], len(threads))
        return t["id"], threads, []

    # ── Messages area render ──────────────────────────────────────────────────

    @app.callback(
        Output(ids.MESSAGES_SCROLL, "children"),
        Input(ids.MESSAGES_STORE, "data"),
        State(ids.THREAD_ID_STORE, "data"),
        State(ids.THEME_STORE, "data"),
    )
    def render_messages(messages, thread_id, theme):
        log.info("render_messages: %d messages, thread=%s", len(messages or []), thread_id)
        from dash import html
        stream_div = html.Div(id=ids.STREAM_MESSAGE)
        if not messages:
            return [welcome_screen(), stream_div]
        rows = [message_row(m, thread_id or "", theme or "light") for m in messages]
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

    # ── Optimistic send: show user bubble + clear composer instantly ──────────
    # Runs client-side so the user message appears the moment Send is pressed,
    # before the (slower) background streaming callback even starts.
    app.clientside_callback(
        """
        function(n_clicks, value, messages) {
            const noUpdate = window.dash_clientside.no_update;
            if (!n_clicks || !value || !value.trim()) {
                return [noUpdate, noUpdate, noUpdate];
            }
            const text = value.trim();
            const msgs = (messages || []).concat([{
                id: "u-" + Date.now(),
                role: "user",
                blocks: [{type: "text", content: text}],
                tool_calls: []
            }]);
            // Reset the composer height after clearing it.
            const el = document.getElementById("composer");
            if (el) { el.style.height = "auto"; el.style.overflowY = "hidden"; }
            return [msgs, "", {text: text, ts: Date.now()}];
        }
        """,
        Output(ids.MESSAGES_STORE, "data", allow_duplicate=True),
        Output(ids.COMPOSER, "value", allow_duplicate=True),
        Output(ids.PENDING_SEND, "data"),
        Input(ids.SEND_BTN, "n_clicks"),
        State(ids.COMPOSER, "value"),
        State(ids.MESSAGES_STORE, "data"),
        prevent_initial_call=True,
    )

    # ── Stop button: clear the in-progress bubble ─────────────────────────────
    # `cancel` forcibly terminates the background job, so it can't clear the
    # streaming bubble itself — do it here the moment Stop is pressed.
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) return window.dash_clientside.no_update;
            return [];
        }
        """,
        Output(ids.STREAM_MESSAGE, "children", allow_duplicate=True),
        Input(ids.STOP_BTN, "n_clicks"),
        prevent_initial_call=True,
    )

    # ── Send message (streaming background callback) ──────────────────────────

    @app.callback(
        Output(ids.MESSAGES_STORE, "data", allow_duplicate=True),
        Input(ids.PENDING_SEND, "data"),
        State(ids.THREAD_ID_STORE, "data"),
        State(ids.MESSAGES_STORE, "data"),
        State(ids.THEME_STORE, "data"),
        background=True,
        manager=background_callback_manager,
        running=[
            # Swap the send button out for the red stop button while streaming.
            (Output(ids.SEND_BTN, "style"), {"display": "none"}, {"display": "flex"}),
            (Output(ids.STOP_BTN, "style"), {"display": "flex"}, {"display": "none"}),
            (Output(ids.COMPOSER, "disabled"), True, False),
        ],
        cancel=[Input(ids.STOP_BTN, "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_send(pending, thread_id, existing_messages, theme):
        if not pending or not pending.get("text"):
            raise PreventUpdate
        theme = theme or "light"

        message = pending["text"].strip()
        if not message:
            raise PreventUpdate

        # The user bubble was already appended optimistically by the client-side
        # callback, so `existing_messages` already includes it.
        messages = list(existing_messages or [])
        first_turn = sum(1 for m in messages if m.get("role") == "user") <= 1

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

        streaming_blocks: list[dict] = []
        tool_calls_acc: list[dict] = []
        status: dict = {"label": "Thinking…"}

        def _push():
            # Inject the whole bubble *including* its `message-row assistant` wrapper —
            # that wrapper supplies the grey background and the centered 860px width, so
            # the streaming bubble matches the final rendered message exactly.
            set_props(ids.STREAM_MESSAGE, {
                "children": streaming_bubble(streaming_blocks, status["label"], theme),
            })

        # Show the animated "Thinking…" status immediately.
        _push()

        try:
            for event in agent_client.stream_message(thread_id, message):
                etype = event.get("event", "message")
                try:
                    data = json.loads(event.get("data", "{}"))
                except json.JSONDecodeError:
                    data = {"content": event.get("data", "")}

                if etype == "status":
                    status["label"] = data.get("label", "Thinking…")
                    _push()

                elif etype == "token":
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
                        # Tokens are arriving → the response is being written.
                        status["label"] = ""
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
                    # After a tool runs the model resumes reasoning.
                    status["label"] = "Thinking…"
                    _push()

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
            log.exception("handle_send: stream failed")
            streaming_blocks.append({"type": "text", "content": f"**Connection error:** {exc}"})
            _push()

        assistant_msg = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "blocks": streaming_blocks,
            "tool_calls": tool_calls_acc,
        }
        set_props(ids.STREAM_MESSAGE, {"children": []})

        # On the first exchange, name the thread after its topic.
        if first_turn:
            try:
                agent_client.generate_title(thread_id)
                set_props(ids.THREADS_DATA_STORE, {"data": agent_client.list_threads()})
            except Exception as e:
                log.warning("generate_title failed: %s", e)

        return messages + [assistant_msg]
