#!/usr/bin/env python3
"""
ワンコマンドで実験パイプラインを順次実行します:
 1) state_transition_visualizer
 2) prob_threshold_extractor_modes
 3) count_sequences
 4) run_llm_eval_batch

使い方: uv run python scripts/run_all.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from experiment_config import DATASET_NAME, ROOT_DIR


def run_visualizer() -> None:
    from src.behavior_pattern_mining.visualization import state_transition_visualizer as stv

    data_file = str(ROOT_DIR / "data" / f"{DATASET_NAME}.csv")
    visualizer = stv.StateTransitionVisualizer()
    visualizer.main(data_file, mode_split=True)


def run_prob_threshold_modes() -> None:
    from src.behavior_pattern_mining.baselines import transition_probability as probm

    probm.main()


def run_count_sequences() -> None:
    from src.behavior_pattern_mining.baselines import frequency as cs

    cs.main()


def run_batch() -> None:
    from src.behavior_pattern_mining.pipelines import llm_eval_batch as batch

    batch.main()


def main() -> None:
    steps = [
        ("state_transition_visualizer", run_visualizer),
        ("prob_threshold_extractor_modes", run_prob_threshold_modes),
        ("count_sequences", run_count_sequences),
        ("run_llm_eval_batch", run_batch),
    ]

    for name, func in steps:
        print(f"\n=== Running: {name} ===")
        try:
            func()
        except Exception as exc:  # pragma: no cover - surface-level runner
            print(f"Error during {name}: {exc}")
            traceback.print_exc()
            print("Aborting pipeline.")
            sys.exit(1)

    print("\nAll steps completed successfully.")


if __name__ == "__main__":
    main()
