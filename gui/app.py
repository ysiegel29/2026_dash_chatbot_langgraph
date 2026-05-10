"""Dash application entrypoint."""
from __future__ import annotations

import logging
import os

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
