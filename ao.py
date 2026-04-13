#!/usr/bin/env python3
"""ao.py — backward-compatible wrapper.

Prefer using the installed `ao` command (pip install alpha-omega).
This script exists for direct invocation: python3 ao.py <command>
"""
import os
import sys

# Ensure the package is importable when running as a script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from alpha_omega.cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
