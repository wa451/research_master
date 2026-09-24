#!/usr/bin/env python3
"""Send one proposed-method request and strictly validate its first response.

This is an API smoke test, not an Evaluation 7 run.  It deliberately sends one
time-band prompt once, without retries or checkpoint reuse, and stores its
separate audit artifacts under the selected model's results directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiment_config import (  # noqa: E402
    BEDROCK_ESTIMATED_OUTPUT_TOKENS,
    BEDROCK_MAX_TOKENS,
    BEDROCK_MODEL_ID,
    BEDROCK_REGION,
    DATASET_NAME,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    current_model_results_root,
)
from src.behavior_pattern_mining.llm.client import (  # noqa: E402
    LLMRuntimeConfig,
    call_llm,
    load_dotenv,
    parse_pattern_records,
    resolve_llm_runtime_config,
)
from src.behavior_pattern_mining.llm.pattern_extractor import (  # noqa: E402
    ENV_FILE_PATH,
    build_mode_user_message,
    find_mode_json_files,
    mode_name_from_path,
    write_json,
)
from src.behavior_pattern_mining.llm.result_paths import (  # noqa: E402
    ensure_model_artifact_directory,
    model_identity,
)


ALLOWED_ADL_LABELS = {
    "Sleep",
    "Wake-up",
    "Meal",
    "Relax",
    "Outing",
    "Hygiene",
    "Toileting",
    "Housework",
    "Work",
    "Other",
}
REQUIRED_RECORD_KEYS = {
    "パターン名",
    "ADL系列ラベル",
    "解釈の根拠",
    "遷移のパターン",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Send exactly one LLM request for one condition/time band and validate "
            "the raw response against the proposed-method JSON contract."
        )
    )
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--n-states", type=int, default=15)
    parser.add_argument("--hamming-threshold", type=int, default=0)
    parser.add_argument(
        "--mode",
        default="Morning",
        help="One state_transition_<mode>.json to send; exactly one request is made.",
    )
    parser.add_argument(
        "--input-modes-dir",
        type=Path,
        default=None,
        help="Directory containing state_transition_<mode>.json files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Fresh directory for smoke-test artifacts. Defaults under results/<model>/api_smoke_tests/.",
    )
    parser.add_argument(
        "--allow-api",
        action="store_true",
        help="Required acknowledgement before this script sends its one paid API request.",
    )
    return parser


def resolve_mode_file(input_modes_dir: Path, mode: str) -> Path:
    """Return one requested time-band JSON, case-insensitively."""
    normalized = mode.strip().casefold()
    matches = [
        path
        for path in find_mode_json_files(input_modes_dir)
        if mode_name_from_path(path).casefold() == normalized
    ]
    if len(matches) != 1:
        available = ", ".join(mode_name_from_path(path) for path in find_mode_json_files(input_modes_dir))
        raise FileNotFoundError(
            f"指定したmode JSONが見つかりません: {mode!r} ({input_modes_dir})。"
            f"利用可能: {available}"
        )
    return matches[0]


def strict_response_errors(raw_response: str, parsed_records: list[dict[str, Any]]) -> list[str]:
    """Return violations of the JSON-only response contract in the prompt."""
    try:
        raw_data = json.loads(raw_response.strip())
    except json.JSONDecodeError as exc:
        return [f"raw response is not a JSON value: {exc.msg}"]

    if not isinstance(raw_data, list):
        return ["top-level response must be a JSON array"]
    if not raw_data:
        return []

    errors: list[str] = []
    for index, record in enumerate(raw_data, start=1):
        prefix = f"record {index}"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be a JSON object")
            continue
        if set(record) != REQUIRED_RECORD_KEYS:
            errors.append(f"{prefix} keys must be exactly {sorted(REQUIRED_RECORD_KEYS)}")
        if not isinstance(record.get("パターン名"), str) or not record["パターン名"].strip():
            errors.append(f"{prefix} パターン名 must be a non-empty string")
        if not isinstance(record.get("解釈の根拠"), str):
            errors.append(f"{prefix} 解釈の根拠 must be a string")
        labels = record.get("ADL系列ラベル")
        if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
            errors.append(f"{prefix} ADL系列ラベル must be a non-empty string array")
        elif invalid_labels := [label for label in labels if label not in ALLOWED_ADL_LABELS]:
            errors.append(f"{prefix} has unsupported ADL labels: {invalid_labels}")
        sequence = record.get("遷移のパターン")
        if (
            not isinstance(sequence, list)
            or not 2 <= len(sequence) <= 4
            or not all(isinstance(state, str) and state.strip() for state in sequence)
        ):
            errors.append(f"{prefix} 遷移のパターン must be a 2-4 item string array")
    if len(parsed_records) != len(raw_data):
        errors.append("parsed record count differs from the raw JSON array")
    return errors


def default_output_dir(
    *,
    model_root: Path,
    dataset: str,
    n_states: int,
    hamming_threshold: int,
    days: int,
    mode: str,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        model_root
        / "api_smoke_tests"
        / f"{dataset}_{n_states}_{hamming_threshold}_{days}days"
        / f"{mode}_{timestamp}"
    )


def run_smoke_test(args: argparse.Namespace) -> Path:
    """Execute exactly one call and write its format-validation artifacts."""
    if not args.allow_api:
        raise RuntimeError("実APIを送信するには --allow-api を明示してください。")
    if args.days <= 0 or args.n_states <= 0 or args.hamming_threshold < 0:
        raise ValueError("daysとn-statesは1以上、hamming-thresholdは0以上で指定してください。")

    load_dotenv(ENV_FILE_PATH)
    llm_config = resolve_llm_runtime_config(
        default_provider=LLM_PROVIDER,
        gemini_model_name=LLM_MODEL_NAME,
        temperature=LLM_TEMPERATURE,
        bedrock_region=BEDROCK_REGION,
        bedrock_model_id=BEDROCK_MODEL_ID,
        bedrock_max_tokens=BEDROCK_MAX_TOKENS,
        bedrock_estimated_output_tokens=BEDROCK_ESTIMATED_OUTPUT_TOKENS,
    )
    identity = model_identity(llm_config.provider, llm_config.model_name)
    input_modes_dir = args.input_modes_dir or (
        ROOT_DIR
        / "picture"
        / f"{DATASET_NAME}_{args.n_states}_{args.hamming_threshold}_{args.days}days"
    )
    mode_path = resolve_mode_file(input_modes_dir, args.mode)
    output_dir = args.output_dir or default_output_dir(
        model_root=current_model_results_root(),
        dataset=DATASET_NAME,
        n_states=args.n_states,
        hamming_threshold=args.hamming_threshold,
        days=args.days,
        mode=mode_name_from_path(mode_path),
    )
    output_dir = output_dir.resolve()
    ensure_model_artifact_directory(
        output_dir,
        identity,
        temperature=llm_config.temperature,
        region=llm_config.region_name,
        max_tokens=llm_config.max_tokens,
        extra={"artifact_kind": "llm_response_smoke_test"},
    )
    validation_path = output_dir / "response_validation.json"
    if validation_path.exists():
        raise RuntimeError(
            f"既存のスモークテスト出力は上書きしません: {validation_path}。"
            "新しい --output-dir を指定してください。"
        )

    user_message = build_mode_user_message(mode_path)
    write_json(
        output_dir / "request.json",
        {
            "request_count": 1,
            "retry_count": 0,
            "dataset": DATASET_NAME,
            "days": args.days,
            "n_states": args.n_states,
            "hamming_threshold": args.hamming_threshold,
            "mode": mode_name_from_path(mode_path),
            "mode_file": str(mode_path),
            "provider": llm_config.provider,
            "model_id": llm_config.model_name,
            "region": llm_config.region_name,
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
            "prompt_sha256": hashlib.sha256(user_message.encode("utf-8")).hexdigest(),
        },
    )

    raw_response, backend, usage, duration_sec = call_llm(llm_config, user_message)
    raw_path = output_dir / "raw_response.txt"
    raw_path.write_text(raw_response, encoding="utf-8")
    try:
        parsed_records = parse_pattern_records(raw_response)
        parse_error = None
    except RuntimeError as exc:
        parsed_records = []
        parse_error = str(exc)
    if parse_error is None:
        write_json(output_dir / "parsed_records.json", parsed_records)

    errors = ([parse_error] if parse_error else []) + strict_response_errors(raw_response, parsed_records)
    validation = {
        "status": "passed" if not errors else "failed",
        "request_count": 1,
        "retry_count": 0,
        "provider": llm_config.provider,
        "model_id": llm_config.model_name,
        "region": llm_config.region_name,
        "mode": mode_name_from_path(mode_path),
        "mode_file": str(mode_path),
        "backend": backend,
        "usage": usage,
        "duration_sec": duration_sec,
        "raw_response_path": str(raw_path),
        "parsed_records_path": str(output_dir / "parsed_records.json") if parse_error is None else None,
        "parsed_record_count": len(parsed_records),
        "strict_format_errors": errors,
    }
    write_json(validation_path, validation)
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if errors:
        raise RuntimeError(
            "LLM応答は既存parserでは処理できない、またはプロンプトの厳密なJSON契約を満たしません。"
            f"詳細: {validation_path}"
        )
    return validation_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validation_path = run_smoke_test(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"API smoke test failed: {exc}", file=sys.stderr)
        return 1
    print(f"API smoke test passed: {validation_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
