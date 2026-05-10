"""Tools for managing artefacts and the virtual filesystem."""
from __future__ import annotations

import base64
import json
import uuid
from typing import Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

def _ok(msg: str, tool_call_id: str | None, **extra_update) -> Command:
    """Return a successful Command with a ToolMessage."""
    tid = tool_call_id or str(uuid.uuid4())
    update = {"messages": [ToolMessage(content=msg, tool_call_id=tid)]}
    update.update(extra_update)
    return Command(update=update)


def _err(msg: str, tool_call_id: str | None) -> Command:
    """Return an error Command with a ToolMessage."""
    tid = tool_call_id or str(uuid.uuid4())
    return Command(update={"messages": [ToolMessage(content=f"Error: {msg}", tool_call_id=tid)]})


# ── Artefact tools ────────────────────────────────────────────────────────────

@tool
def save_artefact(
    name: str,
    content: str,
    artefact_type: str,
    mime_type: str = "application/octet-stream",
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Save a downloadable artefact (file, image, HTML, etc.) for the user.

    Args:
        name: Filename shown in the UI (e.g. "report.pdf").
        content: Base64-encoded bytes for binary; raw text for html/text.
        artefact_type: One of: file | image | plotly | table | html | text.
        mime_type: MIME type for download.
    """
    try:
        artefact = {
            "id": str(uuid.uuid4()), "name": name, "type": artefact_type,
            "content": content, "mime_type": mime_type,
        }
        return _ok(f"Artefact saved: {name}", tool_call_id, artefacts=[artefact])
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


@tool
def render_plotly(
    fig_json: str,
    name: str = "chart.json",
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Render a Plotly figure inline in the chat.

    Args:
        fig_json: JSON string of a Plotly figure (use fig.to_json()).
        name: Display name for the chart.
    """
    try:
        try:
            json.loads(fig_json)
        except json.JSONDecodeError as exc:
            return _err(f"Invalid Plotly JSON: {exc}", tool_call_id)

        artefact = {
            "id": str(uuid.uuid4()), "name": name, "type": "plotly",
            "content": fig_json, "mime_type": "application/json",
        }
        return _ok(f"Chart rendered: {name}", tool_call_id, artefacts=[artefact])
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


@tool
def render_table(
    rows: list[dict],
    name: str = "table",
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Render a data table (ag-grid) inline in the chat.

    Args:
        rows: List of dicts where keys are column names.
        name: Display name for the table.
    """
    try:
        if not rows:
            return _err("No rows to display.", tool_call_id)
        artefact = {
            "id": str(uuid.uuid4()), "name": name, "type": "table",
            "content": json.dumps(rows), "mime_type": "application/json",
        }
        return _ok(f"Table rendered: {name} ({len(rows)} rows)", tool_call_id, artefacts=[artefact])
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


@tool
def render_html(
    html: str,
    name: str = "content.html",
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Render arbitrary HTML in a sandboxed iframe in the chat."""
    try:
        artefact = {
            "id": str(uuid.uuid4()), "name": name, "type": "html",
            "content": html, "mime_type": "text/html",
        }
        return _ok(f"HTML rendered: {name}", tool_call_id, artefacts=[artefact])
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


# ── build_chart: server-side figure construction ─────────────────────────────

@tool
def build_chart(
    chart_type: Literal["scatter", "bar", "line", "pie", "bubble"],
    title: str = "Chart",
    x: list | None = None,
    y: list | None = None,
    labels: list[str] | None = None,
    size: list | None = None,
    color: list | None = None,
    x_title: str = "",
    y_title: str = "",
    name: str = "chart.json",
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Build a Plotly chart server-side from plain Python lists.

    PREFER this over render_plotly when you have more than ~30 data points —
    you pass simple lists and the server constructs the figure JSON, so there
    is NO risk of malformed JSON.

    Args:
        chart_type: "scatter" | "bar" | "line" | "pie" | "bubble"
        title: Chart title.
        x: List of x-axis values (scatter/bar/line/bubble).
        y: List of y-axis values (scatter/bar/line/bubble).
        labels: Hover labels or pie slice names.
        size: Marker sizes for bubble chart (raw values; auto-scaled).
        color: Optional per-point color values or names.
        x_title: X-axis label.
        y_title: Y-axis label.
        name: Display name for the chart artefact.
    """
    try:
        import plotly.graph_objects as go

        if chart_type == "pie":
            trace = go.Pie(
                labels=labels or x or [],
                values=y or [],
                textinfo="label+percent",
            )
            fig = go.Figure(data=[trace])

        elif chart_type == "bubble":
            # Normalise sizes to 6–60px range for readability
            raw_sizes = size or [10] * len(x or [])
            if raw_sizes:
                mn, mx = min(raw_sizes), max(raw_sizes)
                span = mx - mn or 1
                norm = [6 + 54 * (v - mn) / span for v in raw_sizes]
            else:
                norm = []
            trace = go.Scatter(
                x=x or [],
                y=y or [],
                mode="markers",
                text=labels,
                hovertemplate="%{text}<br>x=%{x}<br>y=%{y}<extra></extra>" if labels else None,
                marker=dict(
                    size=norm,
                    color=color or norm,
                    colorscale="Viridis",
                    showscale=bool(color),
                    opacity=0.75,
                    line=dict(width=0.5, color="white"),
                ),
            )
            fig = go.Figure(data=[trace])

        elif chart_type in ("scatter", "line"):
            mode = "markers" if chart_type == "scatter" else "lines+markers"
            trace = go.Scatter(
                x=x or [], y=y or [],
                mode=mode,
                text=labels,
                marker=dict(color=color) if color else {},
            )
            fig = go.Figure(data=[trace])

        elif chart_type == "bar":
            trace = go.Bar(
                x=x or [], y=y or [],
                text=labels,
                marker_color=color,
            )
            fig = go.Figure(data=[trace])

        else:
            return _err(f"Unknown chart_type: {chart_type}", tool_call_id)

        fig.update_layout(
            title=title,
            xaxis_title=x_title,
            yaxis_title=y_title,
            template="plotly_white",
        )

        artefact = {
            "id": str(uuid.uuid4()), "name": name, "type": "plotly",
            "content": fig.to_json(), "mime_type": "application/json",
        }
        return _ok(f"Chart rendered: {name}", tool_call_id, artefacts=[artefact])

    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


# ── Virtual filesystem tools ──────────────────────────────────────────────────

@tool
def write_file(
    path: str,
    content: str,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Write a text file to the virtual filesystem (available to the sandbox).

    Args:
        path: Relative path, e.g. "data/input.csv".
        content: UTF-8 text content.
    """
    try:
        b64 = base64.b64encode(content.encode()).decode()
        return _ok(
            f"Written: {path} ({len(content)} chars)", tool_call_id,
            virtual_files={path: b64},
        )
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


@tool
def read_file(
    path: str,
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """Read a text file from the virtual filesystem."""
    try:
        files = (state or {}).get("virtual_files") or {}
        if path not in files:
            available = list(files.keys()) or ["(none)"]
            text = f"File not found: {path}\nAvailable: {', '.join(available)}"
        else:
            text = base64.b64decode(files[path]).decode("utf-8", errors="replace")
        return _ok(text, tool_call_id)
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)


@tool
def list_files(
    state: Annotated[dict, InjectedState] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
    """List all files currently in the virtual filesystem."""
    try:
        files = (state or {}).get("virtual_files") or {}
        if not files:
            text = "Virtual filesystem is empty."
        else:
            lines = [f"  {p}  ({len(base64.b64decode(b))} bytes)" for p, b in files.items()]
            text = "Files:\n" + "\n".join(lines)
        return _ok(text, tool_call_id)
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}", tool_call_id)
