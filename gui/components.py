"""Rich message rendering.

Each message is a dict:
  {
    "id":    str,
    "role":  "user" | "assistant",
    "blocks": [
      {"type": "text",    "content": str},
      {"type": "plotly",  "content": fig_json_str},
      {"type": "table",   "content": rows_json_str},
      {"type": "html",    "content": html_str},
      {"type": "image",   "content": data_uri_or_url},
      {"type": "artefact","id": str, "name": str, "mime_type": str},
    ],
    "tool_calls": [{"tool": str, "output": str}],  # optional
  }
"""
from __future__ import annotations

import json

import json as _json

import dash_ag_grid as dag
from dash import dcc, html

from . import ids
from .client import get_artefact_url


# ── Artefact chip ─────────────────────────────────────────────────────────────

def artefact_chip(artefact: dict, thread_id: str) -> html.A:
    url = get_artefact_url(thread_id, artefact["id"])
    icon = {
        "image": "🖼", "plotly": "📊", "table": "📋",
        "html": "🌐", "file": "📄", "text": "📝",
    }.get(artefact.get("type", "file"), "📎")
    return html.A(
        [icon, " ", artefact["name"]],
        href=url,
        target="_blank",
        className="artefact-chip",
        download=artefact["name"],
    )


# ── Block renderers ───────────────────────────────────────────────────────────

def _render_text(block: dict) -> html.Div:
    content = block.get("content", "")
    # dcc.Markdown requires a string; LLM may return list of content blocks
    if not isinstance(content, str):
        if isinstance(content, list):
            # Normalise Anthropic-style content blocks to plain text
            content = "".join(
                c.get("text", str(c)) if isinstance(c, dict) else str(c)
                for c in content
            )
        else:
            content = str(content)
    return dcc.Markdown(
        content or "",
        dangerously_allow_html=False,
        className="md-content",
    )


def _render_plotly(block: dict) -> html.Div:
    try:
        content = block.get("content", "{}")
        # Pass the raw dict directly — avoids pio round-trip and plotly version skew
        fig_dict = _json.loads(content) if isinstance(content, str) else content
        return html.Div(
            dcc.Graph(
                figure=fig_dict,
                config={"displayModeBar": True, "responsive": True},
                style={"minHeight": "400px"},
            ),
            className="artefact-embed",
        )
    except Exception as exc:
        return html.Div(
            [html.B("Chart render error: "), html.Code(str(exc))],
            style={"color": "red", "padding": ".5rem"},
        )


def _render_table(block: dict) -> html.Div:
    try:
        rows = _json.loads(block["content"])
        if not rows:
            return html.Span("(empty table)")
        col_defs = [{"field": k, "sortable": True, "filter": True} for k in rows[0].keys()]
        return html.Div(
            dag.AgGrid(
                rowData=rows,
                columnDefs=col_defs,
                defaultColDef={"resizable": True, "minWidth": 80},
                dashGridOptions={"pagination": True, "paginationPageSize": 20},
                style={"height": "320px"},
            ),
            className="artefact-embed",
        )
    except Exception as exc:
        return html.Pre(f"Could not render table: {exc}", style={"color": "red"})


def _render_html(block: dict) -> html.Div:
    return html.Div(
        html.Iframe(
            srcDoc=block["content"],
            sandbox="allow-scripts allow-same-origin",
            style={"width": "100%", "minHeight": "300px", "border": "none"},
        ),
        className="artefact-embed",
    )


def _render_image(block: dict) -> html.Div:
    return html.Div(
        html.Img(
            src=block["content"],
            style={"maxWidth": "100%", "borderRadius": "0.5rem"},
        ),
        className="artefact-embed",
    )


def _render_artefact_inline(block: dict, thread_id: str) -> html.Div:
    atype = block.get("type", "file")
    content = block.get("content", "")

    if atype == "plotly":
        return _render_plotly({"content": content})
    if atype == "table":
        return _render_table({"content": content})
    if atype == "html":
        return _render_html({"content": content})
    if atype == "image":
        # content may be a base64 data URI already
        src = content if content.startswith("data:") else f"data:image/png;base64,{content}"
        return _render_image({"content": src})

    # Generic file → download chip only
    return html.Div(artefact_chip(block, thread_id), className="artefact-bar")


_BLOCK_RENDERERS = {
    "text":     _render_text,
    "markdown": _render_text,
}


def render_blocks(blocks: list[dict], thread_id: str = "") -> list:
    """Convert a list of typed blocks into Dash component children."""
    children = []
    chips = []

    for block in blocks:
        btype = block.get("type", "text")

        if btype in _BLOCK_RENDERERS:
            children.append(_BLOCK_RENDERERS[btype](block))

        elif btype == "plotly":
            children.append(_render_plotly(block))

        elif btype == "table":
            children.append(_render_table(block))

        elif btype == "html":
            children.append(_render_html(block))

        elif btype == "image":
            children.append(_render_image(block))

        elif btype == "artefact":
            # Render inline if it's a visual type; always add a download chip
            if block.get("artefact_type") in ("plotly", "table", "html", "image"):
                children.append(_render_artefact_inline(block, thread_id))
            chips.append(artefact_chip(block, thread_id))

        else:
            children.append(html.Pre(str(block.get("content", ""))))

    if chips:
        children.append(html.Div(chips, className="artefact-bar"))

    return children


# ── Tool call row ─────────────────────────────────────────────────────────────

def tool_row(tool_name: str, output: str) -> html.Details:
    PREVIEW = 400
    preview = output[:PREVIEW] + ("…" if len(output) > PREVIEW else "")
    return html.Details(
        [
            html.Summary([f"⚙ {tool_name}  ", html.Small(f"({len(output)} chars)", style={"opacity": ".6"})]),
            html.Pre(preview, style={"whiteSpace": "pre-wrap", "margin": ".25rem 0 0", "fontSize": ".78rem"}),
        ],
        className="tool-row",
    )


# ── Full message row ──────────────────────────────────────────────────────────

def message_row(msg: dict, thread_id: str = "") -> html.Div:
    role = msg.get("role", "assistant")
    blocks = msg.get("blocks", [])
    tool_calls = msg.get("tool_calls", [])

    content_children = render_blocks(blocks, thread_id)
    tool_children = [tool_row(t["tool"], t.get("output", "")) for t in tool_calls]

    return html.Div(
        [
            html.Div(
                html.Div(content_children, className="bubble"),
                className=f"message-row {role}",
            ),
            *([html.Div(tool_children)] if tool_children else []),
        ],
        id=f"msg-{msg.get('id', '')}",
    )


# ── Streaming placeholder ─────────────────────────────────────────────────────

def streaming_bubble(blocks: list[dict]) -> html.Div:
    """In-progress assistant bubble updated via set_props."""
    content = render_blocks(blocks)
    content.append(html.Span(className="streaming-dot", style={"marginLeft": ".25rem"}))
    return html.Div(
        html.Div(content, className="bubble"),
        className="message-row assistant",
    )


# ── Welcome screen ────────────────────────────────────────────────────────────

EXAMPLE_PROMPTS = [
    "📊  Plot a sine wave and a cosine wave on the same chart.",
    "📋  Make a table of the 10 largest countries by area.",
    "🐍  Write a Python script that generates a Fibonacci sequence.",
    "🔍  Summarise the key ideas in retrieval-augmented generation.",
]


def welcome_screen() -> html.Div:
    prompt_cards = [
        html.Div(
            p,
            className="example-prompt",
            id={"type": "example-prompt", "index": i},
            n_clicks=0,
        )
        for i, p in enumerate(EXAMPLE_PROMPTS)
    ]
    return html.Div(
        [
            html.H2("What can I help you with?"),
            html.P("Start typing below or pick an example.", style={"margin": 0}),
            html.Div(prompt_cards, className="example-prompts"),
        ],
        id=ids.WELCOME_SCREEN,
        className="",
        style={"display": "flex", "flexDirection": "column",
               "alignItems": "center", "justifyContent": "center",
               "height": "100%", "gap": "1.5rem"},
    )
