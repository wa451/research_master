#!/usr/bin/env python3
"""Run the direct-log LLM baseline and evaluate it."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.behavior_pattern_mining.evaluation import direct_log
from src.behavior_pattern_mining.llm import direct_log_extractor


def main() -> None:
    direct_log_extractor.main()
    direct_log.main()


if __name__ == "__main__":
    main()
