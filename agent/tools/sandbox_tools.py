"""Tools that execute code/shell inside the Docker sandbox."""
from __future__ import annotations

import base64
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools.base import InjectedToolCallId
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ..sandbox import run as _sandbox_run

_IGNORE = {"run.py", "__pycache__"}


def _sync_back(original: dict[str, str], output: dict[str, bytes]) -> dict[str, str]:
    updated: dict[str, str] = {}
    for path, content in output.items():
        if any(path == ig or path.endswith(ig) for ig in _IGNORE):
            continue
        b64 = base64.b64encode(content).decode()
        if original.get(path) != b64:
            updated[path] = b64
    return updated


@tool
def run_python(
    code: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Execute Python code in an isolated Docker sandbox (no network).

    The code can read/write files under /workspace, pre-populated with the
    virtual filesystem. New or modified files are synced back into state.
    Returns stdout/stderr output.

    NOTE: For generating Plotly charts, prefer calling render_plotly directly
    with the figure JSON instead of using this tool.
    """
    try:
        virtual_files = state.get("virtual_files") or {}
        script_b64 = base64.b64encode(code.encode()).decode()
        result = _sandbox_run(
            files={**virtual_files, "run.py": script_b64},
            cmd=["python", "run.py"],
        )
        new_files = _sync_back(virtual_files, result.output_files)
        output = result.text()
        return Command(
            update={
                "messages": [ToolMessage(content=output, tool_call_id=tool_call_id)],
                "virtual_files": new_files,
            }
        )
    except Exception as exc:
        return Command(
            update={"messages": [ToolMessage(
                content=f"Sandbox error: {type(exc).__name__}: {exc}",
                tool_call_id=tool_call_id,
            )]}
        )


@tool
def run_shell(
    command: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Execute a shell command in an isolated Docker sandbox (no network).

    The virtual filesystem is available under /workspace.
    New or modified files are synced back into state.
    """
    try:
        virtual_files = state.get("virtual_files") or {}
        result = _sandbox_run(
            files=virtual_files,
            cmd=["sh", "-c", command],
        )
        new_files = _sync_back(virtual_files, result.output_files)
        output = result.text()
        return Command(
            update={
                "messages": [ToolMessage(content=output, tool_call_id=tool_call_id)],
                "virtual_files": new_files,
            }
        )
    except Exception as exc:
        return Command(
            update={"messages": [ToolMessage(
                content=f"Sandbox error: {type(exc).__name__}: {exc}",
                tool_call_id=tool_call_id,
            )]}
        )
