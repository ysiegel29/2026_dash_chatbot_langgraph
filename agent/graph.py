"""Build the LangGraph deep agent."""
from __future__ import annotations

import os

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from .models import get_model
from .state import AgentState
from .tools.artefact_tools import (
    build_chart,
    list_files,
    read_file,
    render_html,
    render_plotly,
    render_table,
    save_artefact,
    write_file,
)
from .tools.mcp_tools import get_mcp_tools
from .tools.sandbox_tools import run_python, run_shell

SYSTEM_PROMPT = """\
You are a capable AI assistant with access to tools for research, data analysis, \
code execution, and rich visual output.

Tool usage guidelines:

CHARTS — use the right tool for the size of data:

  build_chart (PREFERRED for any dataset with more than ~20 points):
    Pass the data as plain Python lists. The server constructs valid Plotly JSON.
    No risk of malformed JSON. Supports: scatter, bubble, bar, line, pie.
    Example bubble chart of countries:
      build_chart(
          chart_type="bubble",
          title="GDP per capita vs Life Expectancy",
          x=[gdp_per_cap_list],   # floats
          y=[life_exp_list],      # floats
          size=[population_list], # floats — auto-scaled
          labels=[country_name_list],
          x_title="GDP per capita (USD)",
          y_title="Life expectancy (years)",
          name="bubble_chart.json"
      )

  render_plotly (only for small hand-crafted figures ≤ 30 points):
    Pass a complete Plotly JSON string. Only use when build_chart is not flexible
    enough and the figure has ≤ 30 data points.

TABLES (render_table):
  - Pass rows as a list of dicts, e.g. [{"col": val, ...}, ...]

HTML (render_html):
  - Pass a full HTML string for rich formatted content.

CODE EXECUTION (run_python / run_shell):
  - Use for data processing, merging datasets, or generating figures from data.
  - The sandbox has NO network access. Use write_file to pass data in as JSON/CSV.
  - If the sandbox image is not built (exit_code=125 / "pull access denied"), skip it
    and build the figure directly with render_plotly using filtered/sampled data.

FILES (write_file / read_file / list_files):
  - Manage the virtual filesystem for sandbox use.

DOWNLOADS (save_artefact):
  - ONLY for binary files the user needs to download: CSV, PDF, images, etc.
  - NEVER use save_artefact for charts or tables — use render_plotly / render_table
    so they appear inline. If you think the data is "too large", filter it first.

Always explain what you are doing in plain language.
"""

# Max chars of a single ToolMessage to include in LLM context.
# Large MCP payloads (e.g. World Bank 100k+ chars) are truncated here;
# the FULL output is still shown in the GUI's tool row.
_MAX_TOOL_CHARS = int(os.environ.get("MAX_TOOL_OUTPUT_CHARS", "20000"))

_LOCAL_TOOLS = [
    build_chart,       # preferred for data arrays; server builds the JSON
    run_python,
    run_shell,
    render_plotly,     # for small hand-crafted figures only
    render_table,
    render_html,
    save_artefact,
    write_file,
    read_file,
    list_files,
]


def _trim_tool_messages(state: dict) -> list:
    """Trim oversized ToolMessage content before the LLM call.

    Returns the full messages list with a prepended SystemMessage. Large tool
    outputs are truncated to _MAX_TOOL_CHARS so they don't exhaust the TPM limit.
    The original content is preserved in the checkpointed state and shown in full
    in the GUI tool row.
    """
    trimmed = []
    for msg in state.get("messages", []):
        if getattr(msg, "type", "") == "tool":
            content = msg.content
            raw = (
                content if isinstance(content, str)
                else "\n".join(
                    b.get("text", str(b)) if isinstance(b, dict) else str(b)
                    for b in content
                ) if isinstance(content, list) else str(content)
            )
            if len(raw) > _MAX_TOOL_CHARS:
                truncated = raw[:_MAX_TOOL_CHARS] + (
                    f"\n…[output truncated — {len(raw):,} chars total, "
                    f"showing first {_MAX_TOOL_CHARS:,}]"
                )
                msg = msg.model_copy(update={"content": truncated})
        trimmed.append(msg)
    return [SystemMessage(content=SYSTEM_PROMPT)] + trimmed


def build_graph(checkpointer, provider: str | None = None,
                model: str | None = None, temperature: float | None = None):
    """Return a compiled LangGraph agent using the supplied async checkpointer."""
    temp = temperature if temperature is not None else float(
        os.environ.get("LLM_TEMPERATURE", "0.7")
    )
    llm = get_model(provider, model, temp)
    all_tools = _LOCAL_TOOLS + get_mcp_tools()

    return create_react_agent(
        model=llm,
        tools=all_tools,
        state_schema=AgentState,
        checkpointer=checkpointer,
        prompt=_trim_tool_messages,   # callable: trims tool output + prepends system msg
    )
