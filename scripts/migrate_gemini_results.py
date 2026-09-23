#!/usr/bin/env python3
"""Copy legacy Gemini-dependent artifacts into results/gemini-2.5-pro.

The migration is intentionally copy-only. Model-independent inputs remain in
``output/``. ``--cleanup-verified`` is an explicit, post-copy operation that
removes only source files whose destination has the identical SHA-256 hash.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behavior_pattern_mining.llm.result_paths import (  # noqa: E402
    ensure_model_artifact_directory,
    model_identity,
    model_results_root,
)


GEMINI = model_identity("google_gemini", "gemini-2.5-pro")
MODEL_DEPENDENT_RESULT_PREFIXES = ("5_", "6_", "7_", "8_", "9_", "10_")
LEGACY_EVALUATION_OUTPUT_PREFIXES = ("5_adl_evaluation", "6_adl_evaluation")


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_under(path: Path) -> Iterable[Path]:
    if not path.exists():
        return ()
    if path.is_file():
        return (path,)
    return (
        item
        for item in sorted(path.rglob("*"))
        if item.is_file() and item.name != ".DS_Store"
    )


def add_tree(plan: dict[Path, Path], source: Path, destination: Path) -> None:
    if source.is_file():
        plan[source] = destination
        return
    for path in files_under(source):
        relative = path.relative_to(source)
        plan[path] = destination / relative


def repair_nested_file_destination(source: Path, destination: Path) -> bool:
    """Repair the initial migration's accidental file.ext/file.ext layout."""
    if not destination.is_dir():
        return False
    nested = destination / destination.name
    entries = list(destination.iterdir())
    if entries != [nested] or not nested.is_file():
        raise RuntimeError(
            f"移行先がファイルではなく、修復可能な二重階層でもありません: {destination}"
        )
    if file_hash(nested) != file_hash(source):
        raise RuntimeError(f"二重階層のhashが移行元と一致しません: {destination}")
    temporary = destination.with_name(f".{destination.name}.migration-repair")
    if temporary.exists():
        raise RuntimeError(f"修復用一時ファイルが既に存在します: {temporary}")
    shutil.copy2(nested, temporary)
    nested.unlink()
    destination.rmdir()
    temporary.replace(destination)
    return True


def build_copy_plan(root: Path) -> tuple[dict[Path, Path], list[Path], list[dict[str, str]]]:
    output = root / "output"
    results = root / "results"
    destination_root = model_results_root(root, GEMINI)
    plan: dict[Path, Path] = {}
    artifact_dirs: set[Path] = set()
    retained: list[dict[str, str]] = []

    # Final evaluation outputs are model-dependent; preserve their existing names.
    if results.exists():
        for source in sorted(results.iterdir()):
            if source.is_dir() and source.name.startswith(MODEL_DEPENDENT_RESULT_PREFIXES):
                add_tree(plan, source, destination_root / source.name)

    # Proposed-method outputs, per-mode checkpoints, failures and usage metrics.
    for condition in sorted(output.glob("aruba_*")):
        selected = [
            path
            for path in condition.iterdir()
            if path.name.startswith("llm_sequences_modes_")
            or path.name.startswith("llm_modes_metrics")
            or path.name.startswith("llm_mode_records_run")
            or path.name == "failed_responses"
        ]
        if selected:
            target = destination_root / condition.name
            artifact_dirs.add(target)
            for source in selected:
                add_tree(plan, source, target / source.name)
        retained.append(
            {
                "source": str(condition),
                "reason": "network/frequency inputs and other non-LLM files remain in output",
            }
        )

    # Direct-log is entirely LLM-generated.
    for source in sorted(output.glob("llm_direct_*")):
        target = destination_root / source.name
        artifact_dirs.add(target)
        add_tree(plan, source, target)

    # Older ADL evaluation directories mix a reusable state series with model outputs.
    for source in sorted(output.iterdir() if output.exists() else []):
        if not source.is_dir() or not source.name.startswith(LEGACY_EVALUATION_OUTPUT_PREFIXES):
            continue
        target = destination_root / source.name
        for path in files_under(source):
            if path.name == "state_series.csv":
                continue
            plan[path] = target / path.relative_to(source)
        retained.append(
            {
                "source": str(source / "state_series.csv"),
                "reason": "model-independent occurrence-search input retained in output",
            }
        )

    # Hestia keeps simulation/preparation in output and mirrors only LLM artifacts.
    hestia_root = output / "9_hestia"
    if hestia_root.exists():
        for source in files_under(hestia_root):
            relative = source.relative_to(hestia_root)
            if "predictions" in relative.parts:
                prediction_index = relative.parts.index("predictions")
                if relative.parts[prediction_index + 1 : prediction_index + 2] != ("llm",):
                    continue
            elif "evaluation" in relative.parts and source.name.startswith("llm_"):
                pass
            elif "runtime" in relative.parts and source.name.startswith("extract_"):
                pass
            else:
                continue
            top = relative.parts[0]
            destination = destination_root / "9_hestia" / top / "artifacts"
            destination /= Path(*relative.parts[1:])
            plan[source] = destination
            if "predictions" in relative.parts:
                llm_index = relative.parts.index("llm")
                artifact_dirs.add(
                    destination_root
                    / "9_hestia"
                    / top
                    / "artifacts"
                    / Path(*relative.parts[1 : llm_index + 1])
                )
        retained.append(
            {
                "source": str(hestia_root),
                "reason": "experiment.json, generated logs, truth, preparation and networks remain in output",
            }
        )

    # SwitchBot preparation stays in output; its LLM fingerprint tree moves logically to results.
    switchbot_root = output / "10_switchbot"
    if switchbot_root.exists():
        for snapshot in sorted(path for path in switchbot_root.iterdir() if path.is_dir()):
            source = snapshot / "llm"
            if source.exists():
                target = destination_root / "10_switchbot" / snapshot.name / "llm"
                add_tree(plan, source, target)
                for fingerprint in source.iterdir():
                    if fingerprint.is_dir():
                        artifact_dirs.add(target / fingerprint.name)
        retained.append(
            {
                "source": str(switchbot_root),
                "reason": "preparation.json, state tables, fixed segments and networks remain in output",
            }
        )

    retained.extend(
        [
            {
                "source": str(output / "cost_estimates"),
                "reason": "cross-model pre-inference estimates intentionally remain in output",
            },
            {
                "source": str(output / "5_adl_correspondence_baselines_fixed"),
                "reason": "model-independent baseline cache remains in output",
            },
        ]
    )
    return plan, sorted(artifact_dirs), retained


def execute_copy_plan(
    plan: dict[Path, Path],
    artifact_dirs: list[Path],
    *,
    dry_run: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    copied: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []
    if not dry_run:
        destination_root = model_results_root(ROOT, GEMINI)
        if not destination_root.exists():
            ensure_model_artifact_directory(
                destination_root,
                GEMINI,
                temperature=0.2,
                extra={"artifact_kind": "model_results_root", "migration": "copy_only"},
            )
        elif not (destination_root / "model_metadata.json").exists():
            raise RuntimeError(
                f"既存の移行先にmodel_metadata.jsonがありません: {destination_root}"
            )
        for directory in artifact_dirs:
            if not directory.exists():
                ensure_model_artifact_directory(
                    directory,
                    GEMINI,
                    temperature=0.2,
                    extra={"artifact_kind": "migrated_legacy_llm_artifacts"},
                )
            elif not (directory / "model_metadata.json").exists():
                raise RuntimeError(
                    f"既存のLLM移行先にmodel_metadata.jsonがありません: {directory}"
                )

    for source, destination in sorted(plan.items(), key=lambda item: str(item[0])):
        source_digest = file_hash(source)
        row = {
            "source": str(source),
            "destination": str(destination),
            "sha256": source_digest,
        }
        if destination.is_dir():
            if dry_run:
                copied.append({**row, "action": "repair_nested_file"})
                continue
            repair_nested_file_destination(source, destination)
        if destination.exists():
            if file_hash(destination) != source_digest:
                raise RuntimeError(f"移行先に内容の異なるファイルがあります: {destination}")
            unchanged.append(row)
            continue
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if file_hash(destination) != source_digest:
                raise RuntimeError(f"コピー後のhash検証に失敗しました: {destination}")
        copied.append(row)
    return copied, unchanged


def cleanup_verified_sources(plan: dict[Path, Path], root: Path) -> tuple[list[str], list[str]]:
    """Delete verified legacy files and prune only their now-empty parents.

    Hash verification for every planned pair completes before the first delete,
    so a partial or mismatched migration cannot remove any legacy artifact.
    ``output/`` and ``results/`` themselves are never removed.
    """
    for source, destination in sorted(plan.items(), key=lambda item: str(item[0])):
        if not source.is_file():
            raise RuntimeError(f"削除対象の移行元ファイルがありません: {source}")
        if not destination.is_file():
            raise RuntimeError(f"削除前の移行先ファイルがありません: {destination}")
        if file_hash(source) != file_hash(destination):
            raise RuntimeError(f"削除前のhash検証に失敗しました: {source}")

    deleted = []
    for source in sorted(plan, key=lambda path: str(path)):
        source.unlink()
        deleted.append(str(source))

    protected_roots = {root / "output", root / "results"}
    pruned: list[str] = []
    parent_candidates = sorted(
        {source.parent for source in plan},
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for parent in parent_candidates:
        current = parent
        while current not in protected_roots and current.is_dir():
            if any(current.iterdir()):
                break
            current.rmdir()
            pruned.append(str(current))
            current = current.parent
    return deleted, pruned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="List and verify the copy plan without writing")
    parser.add_argument(
        "--cleanup-verified",
        action="store_true",
        help="Delete only legacy source files whose copied destination hash matches",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.dry_run and args.cleanup_verified:
        parser.error("--dry-run と --cleanup-verified は同時に指定できません")

    plan, artifact_dirs, retained = build_copy_plan(ROOT)
    copied, unchanged = execute_copy_plan(plan, artifact_dirs, dry_run=args.dry_run)
    deleted: list[str] = []
    pruned: list[str] = []
    if args.cleanup_verified:
        deleted, pruned = cleanup_verified_sources(plan, ROOT)
    payload = {
        "migration": "legacy Gemini artifacts to model-specific results",
        "mode": (
            "dry-run"
            if args.dry_run
            else "cleanup-verified"
            if args.cleanup_verified
            else "copy-only"
        ),
        "model": {
            "provider": GEMINI.provider,
            "model_id": GEMINI.model_id,
            "result_name": GEMINI.result_name,
        },
        "source_files": len(plan),
        "copied_files": len(copied),
        "verified_existing_files": len(unchanged),
        "copied": copied,
        "verified_existing": unchanged,
        "retained_model_independent": retained,
        "source_cleanup_performed": args.cleanup_verified,
        "deleted_source_files": deleted,
        "pruned_empty_source_directories": pruned,
    }
    manifest = args.manifest or (
        model_results_root(ROOT, GEMINI) / "migration_manifest.json"
    )
    if not args.dry_run:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        f"planned={len(plan)} copied={len(copied)} existing={len(unchanged)} "
        f"mode={payload['mode']} deleted={len(deleted)}"
    )
    if not args.dry_run:
        print(f"manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
