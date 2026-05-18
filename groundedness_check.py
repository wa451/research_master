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

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR
from utils.io_utils import write_csv


# =============================
# User settings
# =============================
PROB_THRESHOLD = 0.2
MIN_LEN = 2
MAX_LEN = 4

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

def load_markov_edges(path: Path) -> Dict[Tuple[str, str], float]:
    if not path.exists():
        raise FileNotFoundError(f"Markov graph not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    edges = payload.get("edges", [])
    edge_probs: Dict[Tuple[str, str], float] = {}
    for edge in edges:
        from_state = edge.get("from")
        to_state = edge.get("to")
        prob = edge.get("probability")
        if isinstance(from_state, str) and isinstance(to_state, str) and isinstance(prob, (int, float)):
            edge_probs[(from_state, to_state)] = float(prob)
    return edge_probs


def load_patterns(path: Path) -> List[Tuple[str, List[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Invalid pattern format (list expected): {path}")

    patterns: List[Tuple[str, List[str]]] = []
    for item in payload:
        if isinstance(item, dict):
            seq = item.get("遷移のシーケンス") or item.get("sequence")
            name = item.get("パターン名") or ""
            if isinstance(seq, list) and all(isinstance(s, str) for s in seq):
                patterns.append((str(name), seq))
            continue
        if isinstance(item, list) and all(isinstance(s, str) for s in item):
            patterns.append(("", item))
            continue
        raise ValueError(f"Invalid pattern item: {item}")
    return patterns


def iter_pattern_files(root: Path, pattern: str) -> Iterable[Path]:
    return root.glob(pattern)


def check_sequence(
    sequence: List[str],
    edge_probs: Dict[Tuple[str, str], float],
) -> Tuple[bool, dict]:
    length_ok = MIN_LEN <= len(sequence) <= MAX_LEN
    self_loops: List[str] = []
    missing_edges: List[str] = []
    low_prob_edges: List[str] = []

    for i in range(len(sequence) - 1):
        src = sequence[i]
        dst = sequence[i + 1]
        if src == dst:
            self_loops.append(f"{src}->{dst}")
        prob = edge_probs.get((src, dst))
        if prob is None:
            missing_edges.append(f"{src}->{dst}")
        elif prob < PROB_THRESHOLD:
            low_prob_edges.append(f"{src}->{dst}({prob:.3f})")

    ok = length_ok and not self_loops and not missing_edges and not low_prob_edges
    details = {
        "length_ok": length_ok,
        "self_loops": self_loops,
        "missing_edges": missing_edges,
        "low_prob_edges": low_prob_edges,
    }
    return ok, details


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
