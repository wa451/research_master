#!/usr/bin/env python3
"""Aggregate completed blind human ratings without exposing methods to raters."""

from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


CRITERIA = ["adl_correctness", "rationale_faithfulness", "relevance", "interpretability", "usefulness"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--blind-key", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    ratings, key = pd.read_csv(args.ratings), pd.read_csv(args.blind_key)
    data = ratings.merge(key, on="anonymous_id", how="inner", validate="many_to_one")
    if data.empty:
        raise ValueError("no ratings match the blind key")
    for criterion in CRITERIA:
        data[criterion] = pd.to_numeric(data[criterion], errors="coerce")
    data.to_csv(args.output_dir / "human_evaluation_item_ratings.csv", index=False)
    long = data.melt(id_vars=["anonymous_id", "rater_id", "method"], value_vars=CRITERIA, var_name="criterion", value_name="rating").dropna(subset=["rating"])
    long.groupby(["method", "criterion"], dropna=False)["rating"].agg(["count", "mean", "std"]).reset_index().to_csv(args.output_dir / "human_evaluation_method_summary.csv", index=False)
    long.groupby(["anonymous_id", "criterion"], dropna=False)["rating"].agg(["count", "mean", "std"]).reset_index().to_csv(args.output_dir / "human_evaluation_item_summary.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
