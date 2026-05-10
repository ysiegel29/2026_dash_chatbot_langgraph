#!/usr/bin/env python
"""Fallback launcher: python run_agent.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from agent.service import main
main()
