#!/usr/bin/env python
"""Fallback launcher: python run_gui.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from gui.app import main
main()
