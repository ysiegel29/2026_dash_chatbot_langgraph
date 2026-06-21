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


# Brand-green palettes (shades of --bg-bubble-u) applied to any trace that did not
# set its own colour. Dark mode uses lighter greens so lines stay visible. These
# must stay in sync with the client-side re-theming in ``register_callbacks``.
_GREEN_COLORWAY = {
    "light": ["#039c88", "#43b3a0", "#026e60", "#5cc9b8", "#01786b"],
    "dark":  ["#5cc9b8", "#7ad6c8", "#43b3a0", "#9ae3d8", "#2e9a89"],
}
# Text + gridline colours per theme (also mirrored client-side).
_FONT_COLOR = {"light": "#444444", "dark": "#d0d0d0"}
_GRID_COLOR = {"light": "#e0e0e0", "dark": "#444444"}


def _apply_theme_defaults(fig_dict: dict, theme: str = "light") -> dict:
    """Make a Plotly figure match the chat theme on first paint: transparent
    backgrounds so the bubble colour shows through, a green colourway for unstyled
    traces, and theme-correct font + gridline colours.

    The same values are re-applied client-side in ``register_callbacks`` so charts
    follow live dark/light toggles after they're rendered."""
    if not isinstance(fig_dict, dict):
        return fig_dict
    theme = "dark" if theme == "dark" else "light"
    font = _FONT_COLOR[theme]
    grid = _GRID_COLOR[theme]
    layout = fig_dict.setdefault("layout", {})
    # Force transparent — overrides any template (e.g. plotly_white) baked in.
    layout["paper_bgcolor"] = "rgba(0,0,0,0)"
    layout["plot_bgcolor"] = "rgba(0,0,0,0)"
    layout.setdefault("font", {})["color"] = font
    for axis in ("xaxis", "yaxis"):
        ax = layout.setdefault(axis, {})
        ax["gridcolor"] = grid
        ax["zerolinecolor"] = grid
        ax["linecolor"] = grid
    # Only set a default palette when the figure didn't choose one itself; this
    # leaves explicit per-trace colours and colorscales (e.g. Viridis) untouched.
    layout.setdefault("colorway", _GREEN_COLORWAY[theme])
    return fig_dict


def _render_plotly(block: dict, theme: str = "light") -> html.Div:
    try:
        content = block.get("content", "{}")
        # Pass the raw dict directly — avoids pio round-trip and plotly version skew
        fig_dict = _json.loads(content) if isinstance(content, str) else content
        fig_dict = _apply_theme_defaults(fig_dict, theme)
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
                className="ag-theme-alpine compact-grid",
                defaultColDef={"resizable": True, "minWidth": 80},
                dashGridOptions={
                    "pagination": True,
                    "paginationPageSize": 20,
                    "rowHeight": 24,
                    "headerHeight": 28,
                },
                style={"height": "280px"},
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


def _render_artefact_inline(block: dict, thread_id: str, theme: str = "light") -> html.Div:
    atype = block.get("type", "file")
    content = block.get("content", "")

    if atype == "plotly":
        return _render_plotly({"content": content}, theme)
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


def _split_render(blocks: list[dict], thread_id: str = "", theme: str = "light") -> tuple[list, list]:
    """Render blocks split into (inline, embeds).

    `inline` are text/markdown bits that belong inside the narrow chat bubble.
    `embeds` are charts/tables/html/images/chips that should span the full
    conversation column instead of being squeezed into the bubble's max-width.
    """
    inline: list = []
    embeds: list = []
    chips: list = []

    for block in blocks:
        btype = block.get("type", "text")

        if btype in _BLOCK_RENDERERS:
            content = block.get("content", "")
            # Skip empty text blocks (e.g. tool-calling AI messages) so they
            # don't render as empty bubbles.
            if isinstance(content, str) and not content.strip():
                continue
            inline.append(_BLOCK_RENDERERS[btype](block))

        elif btype == "plotly":
            embeds.append(_render_plotly(block, theme))

        elif btype == "table":
            embeds.append(_render_table(block))

        elif btype == "html":
            embeds.append(_render_html(block))

        elif btype == "image":
            embeds.append(_render_image(block))

        elif btype == "artefact":
            # Render inline if it's a visual type; always add a download chip
            if block.get("artefact_type") in ("plotly", "table", "html", "image"):
                embeds.append(_render_artefact_inline(block, thread_id, theme))
            chips.append(artefact_chip(block, thread_id))

        else:
            inline.append(html.Pre(str(block.get("content", ""))))

    if chips:
        embeds.append(html.Div(chips, className="artefact-bar"))

    return inline, embeds


def render_blocks(blocks: list[dict], thread_id: str = "", theme: str = "light") -> list:
    """Flat render (inline + embeds together). Kept for callers that don't split."""
    inline, embeds = _split_render(blocks, thread_id, theme)
    return inline + embeds


# ── Tool call row ─────────────────────────────────────────────────────────────

def tool_row(tool_name: str, output: str) -> html.Details:
    PREVIEW = 400
    preview = output[:PREVIEW] + ("…" if len(output) > PREVIEW else "")
    return html.Details(
        [
            html.Summary([f"{tool_name}  ", html.Small(f"({len(output)} chars)", style={"opacity": ".6"})]),
            html.Pre(preview, style={"whiteSpace": "pre-wrap", "margin": ".25rem 0 0", "fontSize": ".78rem"}),
        ],
        className="tool-row",
    )


# ── Full message row ──────────────────────────────────────────────────────────

def message_row(msg: dict, thread_id: str = "", theme: str = "light") -> html.Div:
    role = msg.get("role", "assistant")
    blocks = msg.get("blocks", [])
    tool_calls = msg.get("tool_calls", [])

    inline, embeds = _split_render(blocks, thread_id, theme)
    tool_children = [tool_row(t["tool"], t.get("output", "")) for t in tool_calls]

    content = inline + embeds
    # Charts/tables/images stay inside the bubble, but widen it to the full column.
    bubble_cls = "bubble wide" if embeds else "bubble"

    children = []
    if content:  # skip empty messages so they don't render as blank bubbles
        children.append(
            html.Div(
                html.Div(content, className=bubble_cls),
                className=f"message-row {role}",
            )
        )
    if tool_children:
        children.append(html.Div(tool_children))

    return html.Div(children, id=f"msg-{msg.get('id', '')}")


# ── Streaming placeholder ─────────────────────────────────────────────────────

def streaming_bubble(blocks: list[dict], status: str | None = None, theme: str = "light") -> html.Div:
    """In-progress assistant bubble updated via set_props.

    `status` is an animated, Claude-style shimmer line describing what the agent
    is doing right now (e.g. "Thinking…", "Using run_python…"). It is shown while
    work is in progress and cleared once the model starts emitting tokens.
    """
    inline, embeds = _split_render(blocks, theme=theme)

    content = list(inline) + list(embeds)
    if status:
        # Animated shimmer text describing the current step.
        content.append(html.Span(status, className="agent-status"))
    elif not content:
        content.append(html.Span("Thinking…", className="agent-status"))
    else:
        content.append(html.Span(className="streaming-dot", style={"marginLeft": ".25rem"}))

    bubble_cls = "bubble wide" if embeds else "bubble"
    return html.Div(
        html.Div(content, className=bubble_cls),
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
