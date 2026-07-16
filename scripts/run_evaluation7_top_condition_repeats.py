#!/usr/bin/env python3
"""Generate fresh LLM repeats for the top conditions from Evaluation 7 screening."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT_DIR_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(ROOT_DIR_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR_FOR_IMPORTS))

from experiment_config import DATASET_NAME, ROOT_DIR
from src.behavior_pattern_mining.evaluation.evaluation7_staged import (
    select_top_condition_rows,
)
from src.behavior_pattern_mining.llm import pattern_extractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select the top Evaluation 7 screening conditions and generate fresh LLM repeats"
        )
    )
    parser.add_argument("--screening-summary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--total-runs",
        type=int,
        default=3,
        help="Total runs used in the final average, including screening run 1.",
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dataset", default=DATASET_NAME)
    return parser.parse_args()


def expected_pattern_path(
    dataset: str,
    n_states: int,
    hamming_threshold: int,
    days: int,
    run_id: int,
) -> Path:
    suffix = f"{n_states}_{hamming_threshold}_{days}days"
    return (
        ROOT_DIR
        / "output"
        / f"{dataset}_{suffix}"
        / f"llm_sequences_modes_{suffix}_{run_id}.json"
    )


def write_manifest(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("cannot write an empty selected-condition manifest")
    fieldnames = list(rows[0])
    for row in rows[1:]:
        for fieldname in row:
            if fieldname not in fieldnames:
                fieldnames.append(fieldname)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.total_runs < 2:
        raise ValueError("--total-runs must be >= 2")
    if args.dataset != DATASET_NAME:
        raise ValueError(
            f"staged Evaluation 7 extraction currently uses configured dataset {DATASET_NAME!r}; "
            f"received {args.dataset!r}"
        )

    selected = select_top_condition_rows(args.screening_summary, args.top_n)
    generated_run_ids = list(range(2, args.total_runs + 1))
    manifest_rows: list[dict] = []

    for position, row in enumerate(selected, start=1):
        n_states = int(row["n_states"])
        hamming_threshold = int(row["hamming_threshold"])
        row_days = int(row.get("days") or args.days)
        if row_days != args.days:
            raise ValueError(
                f"screening condition K={n_states}, hamming={hamming_threshold} uses "
                f"days={row_days}, expected {args.days}"
            )

        missing_run_ids: list[int] = []
        for run_id in generated_run_ids:
            path = expected_pattern_path(
                args.dataset,
                n_states,
                hamming_threshold,
                args.days,
                run_id,
            )
            if not path.exists():
                missing_run_ids.append(run_id)

        if missing_run_ids:
            print(
                f"[{position}/{len(selected)}] Generating missing runs {missing_run_ids} for "
                f"K={n_states}, hamming={hamming_threshold}"
            )
            pattern_extractor.main(
                days=args.days,
                run_ids=missing_run_ids,
                n_states=n_states,
                hamming_threshold=hamming_threshold,
            )
        else:
            print(
                f"[{position}/{len(selected)}] Skipping K={n_states}, "
                f"hamming={hamming_threshold}; runs {generated_run_ids} already exist"
            )

        missing_outputs: list[Path] = []
        for run_id in generated_run_ids:
            path = expected_pattern_path(
                args.dataset,
                n_states,
                hamming_threshold,
                args.days,
                run_id,
            )
            if not path.exists():
                missing_outputs.append(path)
        if missing_outputs:
            raise RuntimeError(
                "LLM extraction completed without expected outputs: "
                + ", ".join(str(path) for path in missing_outputs)
            )

        manifest_row = dict(row)
        manifest_row["rank"] = position
        manifest_row["condition_id"] = row.get("condition_id") or (
            f"{n_states}_{hamming_threshold}_{args.days}days"
        )
        manifest_row["n_states"] = n_states
        manifest_row["hamming_threshold"] = hamming_threshold
        manifest_row["days"] = args.days
        manifest_rows.append(manifest_row)

    # The manifest doubles as the completion marker, so write it only after all
    # selected conditions have every requested repeat output. It initially carries
    # screening metrics and is replaced with the final multi-run summary afterward.
    write_manifest(args.manifest, manifest_rows)
    print(f"Selected-condition manifest saved to: {args.manifest}")


if __name__ == "__main__":
    main()
