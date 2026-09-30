"""Model-specific output/result paths and provenance for generated artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


MODEL_RESULT_NAMES = {
    "gemini-2.5-pro": "gemini-2.5-pro",
    "us.anthropic.claude-fable-5": "claude-fable-5",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "claude-haiku-4.5",
    "us.anthropic.claude-sonnet-4-6": "claude-sonnet-4.6",
    "us.openai.gpt-5.6-luna": "gpt-5.6-luna",
    "us.openai.gpt-5.6-terra": "gpt-5.6-terra",
    "us.openai.gpt-5.6-sol": "gpt-5.6-sol",
}

_PROVIDER_ALIASES = {
    "gemini": "google_gemini",
    "google": "google_gemini",
    "google_gemini": "google_gemini",
    "bedrock": "bedrock",
}

MODEL_METADATA_FILE = "model_metadata.json"


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model_id: str
    result_name: str


def model_identity(provider: str, model_id: str) -> ModelIdentity:
    return ModelIdentity(
        provider=provider,
        model_id=model_id,
        result_name=result_name_for_model(model_id),
    )


def result_name_for_model(model_id: str) -> str:
    """Return the stable result-directory name for a configured model ID."""
    try:
        return MODEL_RESULT_NAMES[model_id]
    except KeyError as exc:
        supported = ", ".join(sorted(MODEL_RESULT_NAMES))
        raise RuntimeError(
            f"結果ディレクトリ名が未登録のモデルです: {model_id!r}。"
            f" MODEL_RESULT_NAMES に追加してください。登録済み: {supported}"
        ) from exc


def resolve_model_identity(
    *,
    default_provider: str,
    gemini_model_name: str,
    bedrock_model_id: str,
) -> ModelIdentity:
    """Resolve provider/model without requiring API credentials or network access."""
    raw_provider = os.getenv("LLM_PROVIDER", default_provider).strip().lower()
    provider = _PROVIDER_ALIASES.get(raw_provider)
    if provider is None:
        raise RuntimeError(f"未対応の LLM_PROVIDER です: {raw_provider!r}")
    if provider == "google_gemini":
        model_id = os.getenv("GEMINI_MODEL_NAME", gemini_model_name).strip()
    else:
        model_id = os.getenv("BEDROCK_MODEL_ID", bedrock_model_id).strip()
    if not model_id:
        variable = "GEMINI_MODEL_NAME" if provider == "google_gemini" else "BEDROCK_MODEL_ID"
        raise RuntimeError(f"{variable} が未設定です。")
    return model_identity(provider, model_id)


def resolve_project_model_identity(
    project_root: Path,
    *,
    default_provider: str,
    gemini_model_name: str,
    bedrock_model_id: str,
) -> ModelIdentity:
    """Load the project .env, then resolve the active model identity."""
    from src.behavior_pattern_mining.llm.client import load_dotenv

    load_dotenv(project_root / ".env")
    return resolve_model_identity(
        default_provider=default_provider,
        gemini_model_name=gemini_model_name,
        bedrock_model_id=bedrock_model_id,
    )


def model_results_root(project_root: Path, identity: ModelIdentity) -> Path:
    return project_root / "results" / identity.result_name


def model_output_root(project_root: Path, identity: ModelIdentity) -> Path:
    """Return the active model's namespace for generated intermediate artifacts."""
    return project_root / "output" / identity.result_name


def model_result_path(
    project_root: Path,
    identity: ModelIdentity,
    *parts: str | Path,
) -> Path:
    path = model_results_root(project_root, identity)
    for part in parts:
        path /= part
    return path


def model_output_path(
    project_root: Path,
    identity: ModelIdentity,
    *parts: str | Path,
) -> Path:
    path = model_output_root(project_root, identity)
    for part in parts:
        path /= part
    return path


def metadata_payload(
    identity: ModelIdentity,
    *,
    temperature: float | None = None,
    region: str | None = None,
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **asdict(identity),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "temperature": temperature,
        "region": region,
        "max_tokens": max_tokens,
    }
    if extra:
        payload.update(extra)
    return payload


def ensure_model_artifact_directory(
    directory: Path,
    identity: ModelIdentity,
    *,
    temperature: float | None = None,
    region: str | None = None,
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Bind an artifact directory to one model and reject cross-model reuse."""
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path = directory / MODEL_METADATA_FILE
    if metadata_path.exists():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise RuntimeError(f"モデルmetadataの形式が不正です: {metadata_path}")
        existing_identity = (
            existing.get("provider"),
            existing.get("model_id"),
            existing.get("result_name"),
        )
        expected_identity = (identity.provider, identity.model_id, identity.result_name)
        if existing_identity != expected_identity:
            raise RuntimeError(
                "別モデルに紐付いた成果物ディレクトリは再利用できません: "
                f"{directory} ({existing_identity!r} != {expected_identity!r})"
            )
        return metadata_path
    existing_entries = [
        path
        for path in directory.iterdir()
        if path.name not in {".DS_Store", "request.json"}
    ]
    if existing_entries:
        raise RuntimeError(
            "モデルmetadataのない既存成果物ディレクトリは安全に再利用できません: "
            f"{directory}。先に移行スクリプトでモデルへ紐付けてください。"
        )
    metadata_path.write_text(
        json.dumps(
            metadata_payload(
                identity,
                temperature=temperature,
                region=region,
                max_tokens=max_tokens,
                extra=extra,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path
