"""Dash application entrypoint."""
from __future__ import annotations

import logging
import os

# macOS fork-safety: DiskcacheManager runs background callbacks in a subprocess.
# By default `multiprocess` *forks*, but forking the multithreaded Flask server on
# macOS deadlocks/crashes the worker (system libs touch Objective-C/Swift, which is
# unsafe after fork) — the GUI then hangs on "Thinking…" with no output. Forcing the
# "spawn" start method creates a clean fresh process instead, avoiding the issue.
# (`multiprocess` pickles with dill, so the closure-based callbacks still serialize.)
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
try:
    import multiprocess
    multiprocess.set_start_method("spawn", force=True)
except ImportError:
    pass

import dash_bootstrap_components as dbc
import diskcache
from dash import Dash, DiskcacheManager
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def create_app() -> Dash:
    from .callbacks import register_callbacks
    from .layout import build_layout

    cache = diskcache.Cache(os.path.join(os.path.dirname(__file__), "..", "cache"))
    background_callback_manager = DiskcacheManager(cache)

    app = Dash(
        __name__,
        title="AI Assistant",
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        background_callback_manager=background_callback_manager,
        suppress_callback_exceptions=True,
    )

    app.layout = build_layout()

    # Callbacks registered AFTER app instance exists — guaranteed correct binding
    register_callbacks(app, background_callback_manager)

    return app


def main():
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    app = create_app()
    port = int(os.environ.get("GUI_PORT", "8050"))
    app.run(host="127.0.0.1", port=port, debug=True)


if __name__ == "__main__":
    main()
