#!/usr/bin/env python3
"""Run baseline-comparison evaluation for an existing LLM output."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


if __name__ == "__main__":
    runpy.run_module("src.behavior_pattern_mining.evaluation.compare_patterns", run_name="__main__")
