"""Full app layout assembled from components."""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from . import ids
from .models_meta import PROVIDER_MODELS

# ── Navbar ────────────────────────────────────────────────────────────────────

def _provider_model_selects() -> html.Div:
    provider_opts = [{"label": p.upper(), "value": p} for p in PROVIDER_MODELS]
    first_provider = list(PROVIDER_MODELS.keys())[0]
    model_opts = [{"label": m, "value": m} for m in PROVIDER_MODELS[first_provider]]

    return html.Div(
        [
            dbc.Select(
                id=ids.PROVIDER_SELECT,
                options=provider_opts,
                value=first_provider,
                size="sm",
                style={"width": "110px"},
            ),
            dbc.Select(
                id=ids.MODEL_SELECT,
                options=model_opts,
                value=model_opts[0]["value"],
                size="sm",
                style={"width": "180px"},
            ),
        ],
        className="model-selector",
        style={"display": "flex", "gap": ".4rem", "alignItems": "center"},
    )


def navbar() -> html.Div:
    return html.Div(
        [
            html.Span("✦ AI Assistant", className="brand"),
            _provider_model_selects(),
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

def _composer() -> html.Div:
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        dcc.Upload(
                            id=ids.UPLOAD,
                            children=html.Button(
                                "📎",
                                title="Upload file",
                                style={
                                    "background": "none", "border": "none",
                                    "cursor": "pointer", "fontSize": "1.1rem",
                                },
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
        dcc.Store(id=ids.THEME_STORE, storage_type="local", data="light"),
        dcc.Store(id=ids.UPLOAD_STORE, data=None),
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
