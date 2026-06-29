#!/usr/bin/env python3
"""Build representative states, transition networks, and figures."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import DATASET_NAME, ROOT_DIR as PROJECT_ROOT
from src.behavior_pattern_mining.visualization.state_transition_visualizer import (
    StateTransitionVisualizer,
)


def main() -> None:
    data_file = PROJECT_ROOT / "data" / f"{DATASET_NAME}.csv"
    visualizer = StateTransitionVisualizer()
    visualizer.main(str(data_file), mode_split=True)


if __name__ == "__main__":
    main()
