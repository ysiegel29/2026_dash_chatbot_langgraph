# Dash Chatbot + LangGraph Deep Agent

A browser-based chatbot GUI powered by a LangGraph deep agent, with streaming responses, multi-provider LLM support, and a Docker sandbox for safe code execution.

## Architecture

Three processes communicate over HTTP/SSE:

```
Browser (Dash GUI :8050)
        │ HTTP / SSE
        ▼
Agent service (FastAPI :8000)
  ├── LangGraph deep agent
  ├── MCP tool adapters  (http://127.0.0.1:8765/mcp)
  └── SQLite checkpoint (data/checkpoints.db)
        │ docker run
        ▼
Docker sandbox (--network=none, /workspace mount)
```

- **GUI** — Dash app with a thread history sidebar, streaming message rendering (text, markdown, Plotly charts, ag-Grid tables, HTML artefacts), file upload
- **Agent service** — FastAPI + LangGraph with token-level and tool-call SSE streaming; pluggable LLM provider
- **Sandbox** — stateless Docker container with no network access; the agent invokes it via `docker run`

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker (for the sandbox executor)

## Setup

**1. Clone and install dependencies**

```bash
git clone <repo-url>
cd 2026_dash_chatbot_langgraph

# with uv (recommended)
uv sync

# or with pip
pip install -e .
```

**2. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI key (if using OpenAI provider) |
| `ANTHROPIC_API_KEY` | Anthropic key (if using Claude provider) |
| `LLM_PROVIDER` | `openai` \| `anthropic` \| `oss` |
| `LLM_MODEL` | Model name, e.g. `gpt-4o` or `claude-sonnet-4-6` |
| `MCP_URL` | URL of your MCP server (default: `http://127.0.0.1:8765/mcp`) |
| `DB_PATH` | SQLite path for conversation history (default: `data/checkpoints.db`) |

**3. Build the sandbox Docker image**

```bash
docker build -f docker/Dockerfile.sandbox -t deepagent-sandbox:latest .
```

## Running the App

### Option A — Local (two terminals)

```bash
# Terminal 1: start the agent service
uv run python run_agent.py

# Terminal 2: start the GUI
uv run python run_gui.py
```

> The `run_*.py` launchers add the project root to `sys.path` and load `.env`
> themselves, so they work regardless of how the venv resolves editable installs.
> The `start-agent` / `start-gui` console scripts only work if the project root is
> on `PYTHONPATH` (e.g. `uv run --env-file .env start-agent`).

Then open [http://localhost:8050](http://localhost:8050) in your browser.

### Option B — Docker Compose

```bash
docker compose -f docker/compose.yaml up --build
```

Then open [http://localhost:8050](http://localhost:8050).

> Note: The compose file expects `docker/Dockerfile.agent` and `docker/Dockerfile.gui` to exist. See the comments in `docker/compose.yaml` for details.

## Development

```bash
# Install dev extras
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy agent gui
```

## Project Structure

```
2026_dash_chatbot_langgraph/
├── pyproject.toml
├── .env.example
├── run_agent.py          # launcher for agent service (loads .env, fixes sys.path)
├── run_gui.py            # launcher for GUI (loads .env, fixes sys.path)
├── docker/
│   ├── Dockerfile.sandbox
│   └── compose.yaml
├── gui/
│   ├── app.py            # Dash app factory + entrypoint
│   ├── layout.py         # page layout (sidebar, chat, composer)
│   ├── callbacks.py      # all Dash callbacks (incl. streaming send)
│   ├── components.py     # message / block / artefact renderers
│   ├── ids.py            # component id constants
│   ├── models_meta.py    # provider → model lists for the UI
│   └── client.py         # HTTP/SSE client to agent service
├── agent/
│   ├── service.py        # FastAPI app + SSE endpoints
│   ├── graph.py          # LangGraph agent definition
│   ├── state.py          # graph state schema
│   ├── models.py         # LLM provider factory (openai / anthropic / oss)
│   ├── sandbox.py        # Docker sandbox executor
│   ├── tools/            # mcp_tools, sandbox_tools, artefact_tools
│   └── checkpoint_s3.py  # S3 checkpointer stub (not yet active)
├── data/                 # SQLite DB (auto-created)
└── tests/
```

## LLM Providers

Set `LLM_PROVIDER` in `.env` to switch providers without code changes:

| `LLM_PROVIDER` | Required key | Example `LLM_MODEL` |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `oss` | `OSS_API_KEY` + `OSS_BASE_URL` | any vLLM/Ollama model name |

## Troubleshooting

**`ModuleNotFoundError: No module named 'agent'` (or `'gui'`)**
The `start-agent` / `start-gui` console scripts run as script files, and some
uv-managed Python builds skip `.pth` processing for script execution — so the
editable install's path isn't applied. Use the launchers instead, which add the
project root to `sys.path` themselves:

```bash
uv run python run_agent.py
uv run python run_gui.py
```

(If you must use the console scripts, put the project root on `PYTHONPATH`:
`uv run --env-file .env start-agent`.)

**`[Errno 48] Address already in use`**
A previous agent/GUI process is still bound to the port. Clear it:

```bash
lsof -ti:8000 | xargs kill -9   # agent
lsof -ti:8050 | xargs kill -9   # GUI
```

**`DiskcacheManager requires extra dependencies` / `No module named 'multiprocess'`**
The GUI's background callbacks need the `dash[diskcache]` extra. Re-sync deps:

```bash
uv sync
```

**Chat sends but nothing comes back / `Running without MCP tools`**
- Make sure the agent service is running and reachable on `:8000` and that your
  `OPENAI_API_KEY` (or provider key) is set in `.env`.
- `Running without MCP tools` is harmless — the MCP server (`:8765`) is optional;
  the agent still works with its built-in chart/table/code/file tools.
