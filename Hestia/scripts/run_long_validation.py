#!/usr/bin/env python3
"""Execute the required long-run matrix with hashes and resource measurements."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunSpec:
    name: str
    scenario: Path
    days: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    return parser.parse_args()


def run_once(spec: RunSpec, *, seed: int, output_dir: Path) -> dict[str, Any]:
    command = [
        "/usr/bin/time",
        "-lp",
        sys.executable,
        "-m",
        "smart_home_sim.cli",
        "simulate",
        str(spec.scenario),
        "--days",
        str(spec.days),
        "--seed",
        str(seed),
        "--output",
        str(output_dir),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"long-run command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    real_match = re.search(r"(?m)^\s*real\s+([0-9.]+)\s*$", result.stderr)
    rss_match = re.search(r"(?m)^\s*(\d+)\s+maximum resident set size\s*$", result.stderr)
    hash_match = re.search(r"sha256=([0-9a-f]{64})", result.stdout)
    if hash_match is None:
        raise RuntimeError(f"simulation output did not report a hash: {result.stdout}")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "hash": hash_match.group(1),
        "runtime_seconds": float(real_match.group(1)) if real_match else None,
        "max_rss_bytes": int(rss_match.group(1)) if rss_match else None,
        "output_bytes": sum(path.stat().st_size for path in output_dir.iterdir() if path.is_file()),
        "file_count": sum(path.is_file() for path in output_dir.iterdir()),
        "event_count": manifest["event_count"],
        "observed_event_count": manifest.get("observed_event_count"),
        "state_count": manifest["state_count"],
        "semantic_checks_passed": all(manifest["validation"]["semantic"]["checks"].values()),
        "timestamps_sorted": manifest["validation"]["timestamps_sorted"],
        "output_nonempty": all(
            path.stat().st_size > 0 for path in output_dir.iterdir() if path.is_file()
        ),
    }


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    specs = [
        RunSpec(
            "functional_single_7d",
            root / "examples/functional/aruba_single_resident.yaml",
            7,
        ),
        RunSpec(
            "realistic_single_7d",
            root / "examples/realistic_calibrated/aruba_single_resident.yaml",
            7,
        ),
        RunSpec(
            "realistic_single_30d",
            root / "examples/realistic_calibrated/aruba_single_resident.yaml",
            30,
        ),
        RunSpec(
            "realistic_single_220d",
            root / "examples/realistic_calibrated/aruba_single_resident.yaml",
            220,
        ),
        RunSpec(
            "realistic_two_30d",
            root / "examples/realistic_calibrated/two_residents.yaml",
            30,
        ),
        RunSpec(
            "stress_single_7d",
            root / "examples/stress/high_density_single_resident.yaml",
            7,
        ),
        RunSpec(
            "stress_two_noise_7d",
            root / "examples/stress/two_residents_sensor_noise.yaml",
            7,
        ),
    ]
    args.output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        print(f"run {index}/{len(specs)} start: {spec.name}", flush=True)
        primary = run_once(
            spec,
            seed=args.seed,
            output_dir=args.output_root / f"{spec.name}_primary",
        )
        repeat = run_once(
            spec,
            seed=args.seed,
            output_dir=args.output_root / f"{spec.name}_repeat",
        )
        row = {
            "name": spec.name,
            "scenario": str(spec.scenario.relative_to(root)),
            "days": spec.days,
            "seed": args.seed,
            **primary,
            "repeat_hash": repeat["hash"],
            "same_seed_full_directory_match": primary["hash"] == repeat["hash"],
            "repeat_runtime_seconds": repeat["runtime_seconds"],
            "repeat_max_rss_bytes": repeat["max_rss_bytes"],
        }
        rows.append(row)
        print(
            f"run {index}/{len(specs)} complete: events={primary['event_count']}, "
            f"hash_match={row['same_seed_full_directory_match']}",
            flush=True,
        )
    diversity_spec = specs[1]
    different = run_once(
        diversity_spec,
        seed=args.seed + 1,
        output_dir=args.output_root / "realistic_single_7d_different_seed",
    )
    diversity_hash_changed = different["hash"] != rows[1]["hash"]
    rows[1]["different_seed"] = args.seed + 1
    rows[1]["different_seed_hash"] = different["hash"]
    rows[1]["different_seed_hash_changed"] = diversity_hash_changed

    args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with args.summary_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "runs": rows,
        "all_same_seed_hashes_match": all(row["same_seed_full_directory_match"] for row in rows),
        "all_semantic_checks_passed": all(row["semantic_checks_passed"] for row in rows),
        "all_outputs_nonempty": all(row["output_nonempty"] for row in rows),
        "different_seed_hash_changed": diversity_hash_changed,
    }
    args.summary_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown = [
        "# 改善後長期実行検証",
        "",
        "| 実行 | 日数 | events | states | 秒 | 最大RSS | 出力 | 同seed一致 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    markdown.extend(
        f"| {row['name']} | {row['days']} | {row['event_count']} | {row['state_count']} | "
        f"{float(row['runtime_seconds'] or 0):.3f} | {int(row['max_rss_bytes'] or 0)} | "
        f"{row['output_bytes']} | {row['same_seed_full_directory_match']} |"
        for row in rows
    )
    markdown.extend(
        [
            "",
            "## 結論",
            "",
            f"- 全意味検証成功: `{payload['all_semantic_checks_passed']}`",
            f"- 全出力非空: `{payload['all_outputs_nonempty']}`",
            f"- 同seed完全ディレクトリハッシュ一致: `{payload['all_same_seed_hashes_match']}`",
            f"- realistic 7日で別seedハッシュ変化: `{payload['different_seed_hash_changed']}`",
            "- 最大RSSと出力サイズは各行の実測値。生成物は`/private/tmp`に置き、"
            "Git管理対象にしていない。",
        ]
    )
    args.summary_md.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
