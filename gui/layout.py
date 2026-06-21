"""Full app layout assembled from components."""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from . import ids

# ── Navbar ────────────────────────────────────────────────────────────────────

def navbar() -> html.Div:
    return html.Div(
        [
            html.Span("AI Assistant", className="brand"),
            html.Button("🌙", id=ids.THEME_TOGGLE, title="Toggle dark/light mode"),
        ],
        id="navbar",
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar() -> html.Div:
    return html.Div(
        [
            html.Div(
                dbc.Button(
                    "+ New chat",
                    id=ids.NEW_CHAT_BTN,
                    color="primary",
                    size="sm",
                    className="w-100",
                ),
                id="sidebar-header",
            ),
            html.Div(id=ids.THREAD_LIST),
        ],
        id="sidebar",
    )


# ── Chat area ─────────────────────────────────────────────────────────────────

# Flat (stroke) paperclip icon as an inline SVG data URI — no emoji.
_PAPERCLIP_SVG = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' "
    "viewBox='0 0 24 24' fill='none' stroke='%236c757d' stroke-width='2' "
    "stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21.44 11.05l-9.19 "
    "9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48'/"
    "%3E%3C/svg%3E"
)


def _composer() -> html.Div:
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        dcc.Upload(
                            id=ids.UPLOAD,
                            className="attach-btn",
                            children=html.Img(
                                src=_PAPERCLIP_SVG,
                                className="attach-icon",
                                title="Upload file",
                            ),
                            multiple=False,
                        ),
                        dcc.Textarea(
                            id=ids.COMPOSER,
                            placeholder="Message… (Enter to send, Shift+Enter for newline)",
                            rows=1,
                            style={"width": "100%"},
                        ),
                        html.Button("➤", id=ids.SEND_BTN, title="Send (Enter)"),
                        html.Button(
                            html.Span(className="stop-icon"),
                            id=ids.STOP_BTN,
                            title="Stop generating",
                            style={"display": "none"},
                        ),
                    ],
                    id="composer-row",
                ),

            ],
            id="composer-inner",
        ),
        id="composer-wrap",
    )


def chat_area() -> html.Div:
    return html.Div(
        [
            # Start empty — render_messages callback populates this on first load
            html.Div([], id=ids.MESSAGES_SCROLL),
            _composer(),
        ],
        id="chat-area",
    )


# ── Hidden stores ─────────────────────────────────────────────────────────────

def stores() -> list:
    return [
        dcc.Store(id=ids.THREAD_ID_STORE, storage_type="local"),
        dcc.Store(id=ids.THREADS_DATA_STORE, data=[]),
        dcc.Store(id=ids.MESSAGES_STORE, data=[]),
        dcc.Store(id=ids.PENDING_SEND, data=None),
        dcc.Store(id=ids.THEME_STORE, storage_type="local", data="light"),
        dcc.Store(id=ids.UPLOAD_STORE, data=None),
        dcc.Store(id=ids.GRAPH_THEME_DUMMY),
        dcc.Download(id="artefact-download"),
        # Fires exactly once on page load to bootstrap thread list
        dcc.Interval(id="init-interval", interval=200, max_intervals=1),
    ]


# ── Root ──────────────────────────────────────────────────────────────────────

def build_layout() -> html.Div:
    return html.Div(
        [
            *stores(),
            navbar(),
            html.Div(
                [sidebar(), chat_area()],
                id="main-row",
            ),
        ],
        id="app-root",
    )
