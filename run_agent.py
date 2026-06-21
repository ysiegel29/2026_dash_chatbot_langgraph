#!/usr/bin/env python
"""Fallback launcher: python run_agent.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()
from agent.service import main

# NOTE: the __main__ guard is REQUIRED. uvicorn's reload=True uses multiprocessing
# "spawn", which re-imports this module in the worker process. Without the guard,
# the worker would re-run main() and start a second server → "[Errno 48] Address
# already in use".
if __name__ == "__main__":
    main()
