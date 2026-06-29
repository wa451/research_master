"""
Groundedness checker for LLM-generated sequences.

Checks:
- Edge exists in Markov graph and probability >= threshold
- Sequence length within [MIN_LEN, MAX_LEN]
- No self-loop transitions (A->A)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import re

from experiment_config import (
    DATASET_NAME,
    DAYS,
    HAMMING_THRESHOLD,
    MAX_SEQUENCE_LENGTH,
    MIN_SEQUENCE_LENGTH,
    N_STATES,
    ROOT_DIR,
    TRANSITION_PROBABILITY_THRESHOLD,
)
from src.behavior_pattern_mining.evaluation.groundedness import (
    check_sequence as check_sequence_core,
    iter_pattern_files,
    load_markov_edges,
    load_patterns,
)
from src.behavior_pattern_mining.io.csv_io import write_csv


# =============================
# User settings
# =============================
PROB_THRESHOLD = TRANSITION_PROBABILITY_THRESHOLD
MIN_LEN = MIN_SEQUENCE_LENGTH
MAX_LEN = MAX_SEQUENCE_LENGTH

MARKOV_GRAPH_PATH = (
    ROOT_DIR
    / "picture"
    / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
    / "state_transition_all.json"
)

# RUN_OUTPUT_DIR = (
#     ROOT_DIR
#     / "output"
#     / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
# )
# PATTERN_GLOB = f"llm_sequences_modes_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days_*.json"

RUN_OUTPUT_DIR = (
    ROOT_DIR
    / "output"
    / f"llm_direct_{DAYS}"
)
PATTERN_GLOB = f"*.json"

def check_sequence(
    sequence: List[str],
    edge_probs: Dict[Tuple[str, str], float],
) -> Tuple[bool, dict]:
    return check_sequence_core(
        sequence=sequence,
        edge_probs=edge_probs,
        probability_threshold=PROB_THRESHOLD,
        min_len=MIN_LEN,
        max_len=MAX_LEN,
    )


def main() -> None:
    edge_probs = load_markov_edges(MARKOV_GRAPH_PATH)

    if not RUN_OUTPUT_DIR.exists():
        raise FileNotFoundError(f"Output folder not found: {RUN_OUTPUT_DIR}")

    pattern_files = list(iter_pattern_files(RUN_OUTPUT_DIR, PATTERN_GLOB))
    if not pattern_files:
        raise FileNotFoundError(
            f"No pattern files found with glob: {PATTERN_GLOB} (root: {RUN_OUTPUT_DIR})"
        )

    summary_rows: List[dict] = []

    for pattern_path in pattern_files:
        patterns = load_patterns(pattern_path)
        grounded_count = 0

        for idx, (name, seq) in enumerate(patterns, start=1):
            ok, details = check_sequence(seq, edge_probs)
            if ok:
                grounded_count += 1

        grounded_rate = grounded_count / len(patterns) if patterns else 0.0

        # extract numeric run id from filename suffix like "_1" or "run1"
        m = re.search(r"_(\d+)$", pattern_path.stem)
        if m:
            run_val = int(m.group(1))
        else:
            m2 = re.search(r"run(\d+)$", pattern_path.stem)
            run_val = int(m2.group(1)) if m2 else pattern_path.stem

        summary_rows.append(
            {
                "run": run_val,
                "total_patterns": len(patterns),
                "grounded_count": grounded_count,
                "grounded_rate": f"{grounded_rate:.4f}",
            }
        )

    # sort by numeric run if possible
    try:
        summary_rows.sort(key=lambda r: int(r["run"]))
    except Exception:
        summary_rows.sort(key=lambda r: str(r["run"]))

    report_path = RUN_OUTPUT_DIR / f"groundedness_all_runs_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days.csv"
    write_csv(
        report_path,
        summary_rows,
        fieldnames=[
            "run",
            "total_patterns",
            "grounded_count",
            "grounded_rate",
        ],
    )

    print(f"Groundedness report saved: {report_path}")


if __name__ == "__main__":
    main()
