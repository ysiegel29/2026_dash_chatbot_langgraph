#!/usr/bin/env python
"""Fallback launcher: python run_gui.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
from gui.app import main

# Guard required: Dash debug reloader / spawn-based background workers re-import
# __main__. Without it, the child would re-run main() and double-bind the port.
if __name__ == "__main__":
    main()
