#!/usr/bin/env python3
"""Run condition-based sequence evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.behavior_pattern_mining.evaluation.condition_metrics import main


if __name__ == "__main__":
    main()
