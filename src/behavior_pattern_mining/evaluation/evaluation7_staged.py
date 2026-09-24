"""Shared Evaluation 7 protocol constants and optional staged-selection helpers."""

from __future__ import annotations

import csv
from pathlib import Path


REQUIRED_CONDITION_FIELDS = {"n_states", "hamming_threshold"}

# Formal Evaluation 7 protocol.  The optional staged helpers below are retained
# only for reproducing earlier exploratory runs.
FORMAL_EVALUATION7_N_STATES = (10, 15, 20, 25, 30, 35, 40)
FORMAL_EVALUATION7_HAMMING = (0, 1, 2, 3)
FORMAL_EVALUATION7_DAYS = 14
FORMAL_EVALUATION7_RUNS = 5
FORMAL_EVALUATION7_RESULTS_DIRNAME = "7_param_search_14d_5runs"


def load_condition_rows(path: Path) -> list[dict[str, str]]:
    """Load and validate condition rows from a CSV summary or manifest."""
    if not path.exists():
        raise FileNotFoundError(f"condition file does not exist: {path}")

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_CONDITION_FIELDS - fieldnames)
        if missing:
            raise ValueError(
                f"condition file is missing required columns {missing}: {path}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError(f"condition file contains no rows: {path}")
    return rows


def condition_pairs_from_file(path: Path, *, expected_days: int | None = None) -> list[tuple[int, int]]:
    """Return unique ``(K, hamming)`` pairs in file order."""
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for row in load_condition_rows(path):
        pair = (int(row["n_states"]), int(row["hamming_threshold"]))
        if pair in seen:
            raise ValueError(f"duplicate condition {pair} in {path}")
        if expected_days is not None and str(row.get("days") or "").strip():
            row_days = int(row["days"])
            if row_days != expected_days:
                raise ValueError(
                    f"condition {pair} has days={row_days}, expected {expected_days}: {path}"
                )
        seen.add(pair)
        pairs.append(pair)
    return pairs


def select_top_condition_rows(summary_path: Path, top_n: int) -> list[dict[str, str]]:
    """Select the top ranked conditions from an Evaluation 7 summary CSV."""
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    rows = load_condition_rows(summary_path)
    if len(rows) < top_n:
        raise ValueError(
            f"requested top {top_n}, but screening summary has only {len(rows)} conditions: "
            f"{summary_path}"
        )

    if all(str(row.get("rank") or "").strip() for row in rows):
        rows.sort(key=lambda row: int(row["rank"]))
    elif all(str(row.get("selection_metric_value") or "").strip() for row in rows):
        rows.sort(key=lambda row: -float(row["selection_metric_value"]))
    else:
        raise ValueError(
            "screening summary must contain rank or selection_metric_value for every row: "
            f"{summary_path}"
        )

    selected = rows[:top_n]
    # Reuse the common validator for duplicate pairs before returning the selection.
    seen: set[tuple[int, int]] = set()
    for row in selected:
        pair = (int(row["n_states"]), int(row["hamming_threshold"]))
        if pair in seen:
            raise ValueError(f"duplicate selected condition {pair} in {summary_path}")
        seen.add(pair)
    return selected
