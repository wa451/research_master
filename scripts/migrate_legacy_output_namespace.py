#!/usr/bin/env python3
"""Move legacy root-level output artifacts into one model namespace safely.

New generated artifacts live under ``output/<model>/``.  This utility assigns
the pre-namespace ``output/`` tree to a model (Gemini 2.5 Pro by default),
copies every file with SHA-256 verification, and deletes originals only with
the explicit ``--cleanup-verified`` option.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migrate_gemini_results import cleanup_verified_sources, file_hash  # noqa: E402
from src.behavior_pattern_mining.llm.result_paths import (  # noqa: E402
    MODEL_RESULT_NAMES,
    ensure_model_artifact_directory,
    model_identity,
    model_output_root,
)


def files_under(path: Path) -> list[Path]:
    if path.is_file():
        return [] if path.name == ".DS_Store" else [path]
    return [item for item in sorted(path.rglob("*")) if item.is_file() and item.name != ".DS_Store"]


def build_copy_plan(root: Path, *, result_name: str) -> dict[Path, Path]:
    """Map only legacy root-level output files; never re-copy namespaces."""
    output_root = root / "output"
    destination_root = output_root / result_name
    if not output_root.exists():
        return {}

    model_names = set(MODEL_RESULT_NAMES.values())
    plan: dict[Path, Path] = {}
    for source in sorted(output_root.iterdir()):
        if source.name in model_names or source.name == ".DS_Store":
            continue
        for file_path in files_under(source):
            plan[file_path] = destination_root / file_path.relative_to(output_root)
    return plan


def execute_copy_plan(
    plan: dict[Path, Path],
    *,
    root: Path,
    provider: str,
    model_id: str,
    dry_run: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    identity = model_identity(provider, model_id)
    destination_root = model_output_root(root, identity)
    copied: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []
    if not dry_run and not destination_root.exists():
        ensure_model_artifact_directory(
            destination_root,
            identity,
            temperature=0.2,
            extra={"artifact_kind": "model_output_root", "migration": "legacy_output_namespace"},
        )
    elif not dry_run and not (destination_root / "model_metadata.json").is_file():
        raise RuntimeError(f"既存の移行先にmodel_metadata.jsonがありません: {destination_root}")

    for source, destination in sorted(plan.items(), key=lambda item: str(item[0])):
        source_digest = file_hash(source)
        row = {"source": str(source), "destination": str(destination), "sha256": source_digest}
        if destination.exists():
            if not destination.is_file() or file_hash(destination) != source_digest:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="google_gemini")
    parser.add_argument("--model-id", default="gemini-2.5-pro")
    parser.add_argument("--dry-run", action="store_true", help="移行対象だけ表示し、ファイルを変更しない")
    parser.add_argument(
        "--cleanup-verified",
        action="store_true",
        help="hash一致を全件確認後に旧output直下の移行元だけを削除する",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.dry_run and args.cleanup_verified:
        parser.error("--dry-run と --cleanup-verified は同時に指定できません")

    identity = model_identity(args.provider, args.model_id)
    plan = build_copy_plan(ROOT, result_name=identity.result_name)
    copied, unchanged = execute_copy_plan(
        plan,
        root=ROOT,
        provider=identity.provider,
        model_id=identity.model_id,
        dry_run=args.dry_run,
    )
    deleted: list[str] = []
    pruned: list[str] = []
    if args.cleanup_verified:
        deleted, pruned = cleanup_verified_sources(plan, ROOT)

    payload = {
        "migration": "legacy root output to model-specific output namespace",
        "mode": "dry-run" if args.dry_run else "cleanup-verified" if args.cleanup_verified else "copy-only",
        "model": {"provider": identity.provider, "model_id": identity.model_id, "result_name": identity.result_name},
        "source_files": len(plan),
        "copied_files": len(copied),
        "verified_existing_files": len(unchanged),
        "copied": copied,
        "verified_existing": unchanged,
        "source_cleanup_performed": args.cleanup_verified,
        "deleted_source_files": deleted,
        "pruned_empty_source_directories": pruned,
    }
    manifest = args.manifest or (model_output_root(ROOT, identity) / "migration_manifest.json")
    if not args.dry_run:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"planned={len(plan)} copied={len(copied)} existing={len(unchanged)} mode={payload['mode']} deleted={len(deleted)}")
    if not args.dry_run:
        print(f"manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
