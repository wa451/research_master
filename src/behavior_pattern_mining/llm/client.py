"""Shared helpers for LLM extraction scripts."""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from botocore.config import Config


@dataclass(frozen=True)
class LLMRuntimeConfig:
    """Validated provider settings used by the shared LLM adapter."""

    provider: str
    model_name: str
    temperature: Optional[float]
    api_key: Optional[str] = None
    region_name: Optional[str] = None
    max_tokens: Optional[int] = None
    estimated_output_tokens: Optional[int] = None


@dataclass(frozen=True)
class BedrockInputTokenCount:
    """Aggregate CountTokens result with explicit exact/approximate provenance."""

    total_tokens: int
    exact: bool
    method: str
    warning: Optional[str] = None


# Keep the SDK retry budget deliberately small.  A read timeout can be
# ambiguous (the service may still finish the inference), and some callers
# have checkpoint-aware resume logic above this layer.
DEFAULT_BEDROCK_READ_TIMEOUT_SECONDS = 600
DEFAULT_BEDROCK_CONNECT_TIMEOUT_SECONDS = 60
DEFAULT_BEDROCK_RETRY_MODE = "standard"
DEFAULT_BEDROCK_MAX_ATTEMPTS = 2
SUPPORTED_BEDROCK_RETRY_MODES = {"legacy", "standard", "adaptive"}
FABLE_DATA_RETENTION_MAX_ATTEMPTS = 3


def bedrock_supports_temperature(model_name: str) -> bool:
    """Return whether a Bedrock Converse model accepts ``temperature``."""
    normalized_model_name = model_name.strip().lower()
    if normalized_model_name.startswith(
        ("us.openai.gpt-5.6-", "global.openai.gpt-5.6-")
    ):
        return False
    return normalized_model_name not in {
        "anthropic.claude-fable-5",
        "global.anthropic.claude-fable-5",
        "us.anthropic.claude-fable-5",
    }


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer timeout/retry setting without silent fallback."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} は1以上の整数で指定してください。") from exc
    if value < 1:
        raise RuntimeError(f"{name} は1以上の整数で指定してください。")
    return value


def bedrock_runtime_client_config() -> Config:
    """Return the shared, bounded Botocore configuration for Bedrock calls.

    ``total_max_attempts`` includes the first request.  The default of two
    therefore permits one SDK-managed retry, with standard exponential backoff.
    """
    read_timeout = _positive_int_env(
        "BEDROCK_READ_TIMEOUT_SECONDS", DEFAULT_BEDROCK_READ_TIMEOUT_SECONDS
    )
    connect_timeout = _positive_int_env(
        "BEDROCK_CONNECT_TIMEOUT_SECONDS", DEFAULT_BEDROCK_CONNECT_TIMEOUT_SECONDS
    )
    max_attempts = _positive_int_env(
        "BEDROCK_MAX_ATTEMPTS", DEFAULT_BEDROCK_MAX_ATTEMPTS
    )
    retry_mode = os.getenv("BEDROCK_RETRY_MODE", DEFAULT_BEDROCK_RETRY_MODE).strip().lower()
    if retry_mode not in SUPPORTED_BEDROCK_RETRY_MODES:
        supported = ", ".join(sorted(SUPPORTED_BEDROCK_RETRY_MODES))
        raise RuntimeError(
            f"BEDROCK_RETRY_MODE は次のいずれかを指定してください: {supported}"
        )
    return Config(
        read_timeout=read_timeout,
        connect_timeout=connect_timeout,
        retries={"mode": retry_mode, "total_max_attempts": max_attempts},
    )


def create_bedrock_runtime_client(region_name: str) -> Any:
    """Create the only Bedrock Runtime client used by execution and estimates."""
    try:
        boto3 = importlib.import_module("boto3")
    except ImportError as exc:
        raise RuntimeError(
            "Bedrock実行には boto3 が必要です。uv sync または pip install boto3 を実行してください。"
        ) from exc
    return boto3.client(
        "bedrock-runtime",
        region_name=region_name,
        config=bedrock_runtime_client_config(),
    )


def resolve_llm_runtime_config(
    *,
    default_provider: str,
    gemini_model_name: str,
    temperature: float,
    bedrock_region: str,
    bedrock_model_id: str,
    bedrock_max_tokens: int,
    bedrock_estimated_output_tokens: Optional[int],
) -> LLMRuntimeConfig:
    """Resolve provider settings after ``load_dotenv`` has been called.

    Environment variables override non-secret defaults from ``configs/default.yaml``.
    AWS credentials deliberately are not accepted here; boto3 uses its standard
    credential chain.
    """
    raw_provider = os.getenv("LLM_PROVIDER", default_provider).strip().lower()
    provider_aliases = {
        "gemini": "google_gemini",
        "google": "google_gemini",
        "google_gemini": "google_gemini",
        "bedrock": "bedrock",
    }
    provider = provider_aliases.get(raw_provider)
    if provider is None:
        supported = ", ".join(sorted({"google_gemini", "bedrock"}))
        raise RuntimeError(
            f"未対応の LLM_PROVIDER です: {raw_provider!r}。"
            f"利用可能な値: {supported}"
        )

    if provider == "google_gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=google_gemini ですが GEMINI_API_KEY が未設定です。"
                "リポジトリ直下の .env または環境変数に設定してください。"
            )
        model_name = os.getenv("GEMINI_MODEL_NAME", gemini_model_name).strip()
        if not model_name:
            raise RuntimeError("Geminiのモデル名が未設定です。")
        return LLMRuntimeConfig(
            provider=provider,
            model_name=model_name,
            temperature=temperature,
            api_key=api_key,
        )

    region_name = (
        os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or bedrock_region.strip()
    )
    model_name = os.getenv("BEDROCK_MODEL_ID", bedrock_model_id).strip()
    raw_max_tokens = os.getenv("BEDROCK_MAX_TOKENS", str(bedrock_max_tokens)).strip()
    try:
        max_tokens = int(raw_max_tokens)
    except ValueError as exc:
        raise RuntimeError("BEDROCK_MAX_TOKENS は整数で指定してください。") from exc
    raw_estimated_output_tokens = os.getenv("BEDROCK_ESTIMATED_OUTPUT_TOKENS", "").strip()
    if raw_estimated_output_tokens:
        try:
            estimated_output_tokens = int(raw_estimated_output_tokens)
        except ValueError as exc:
            raise RuntimeError(
                "BEDROCK_ESTIMATED_OUTPUT_TOKENS は整数で指定してください。"
            ) from exc
    else:
        estimated_output_tokens = bedrock_estimated_output_tokens

    if not region_name:
        raise RuntimeError(
            "LLM_PROVIDER=bedrock ですが AWS_REGION が未設定です。"
            ".env、環境変数、または configs/default.yaml に設定してください。"
        )
    if not model_name:
        raise RuntimeError(
            "LLM_PROVIDER=bedrock ですが BEDROCK_MODEL_ID が未設定です。"
            ".env または configs/default.yaml に利用可能なmodelIdを設定してください。"
        )
    if max_tokens <= 0:
        raise RuntimeError("BEDROCK_MAX_TOKENS は1以上で指定してください。")
    if estimated_output_tokens is not None and estimated_output_tokens < 0:
        raise RuntimeError("BEDROCK_ESTIMATED_OUTPUT_TOKENS は0以上で指定してください。")
    if estimated_output_tokens is not None and estimated_output_tokens > max_tokens:
        raise RuntimeError(
            "BEDROCK_ESTIMATED_OUTPUT_TOKENS は BEDROCK_MAX_TOKENS 以下で指定してください。"
        )

    effective_temperature = temperature if bedrock_supports_temperature(model_name) else None
    return LLMRuntimeConfig(
        provider=provider,
        model_name=model_name,
        temperature=effective_temperature,
        region_name=region_name,
        max_tokens=max_tokens,
        estimated_output_tokens=estimated_output_tokens,
    )


def load_dotenv(env_file_path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into environment variables."""
    if not env_file_path.exists():
        return

    for raw_line in env_file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _balanced_json_snippets(text: str) -> Iterable[str]:
    """Yield balanced JSON-looking object/array snippets from mixed text."""
    starts = [i for i, ch in enumerate(text) if ch in "[{"]
    for start in starts:
        stack: List[str] = []
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch in "[{":
                stack.append(ch)
            elif ch in "]}":
                if not stack:
                    break
                opener = stack.pop()
                if (opener, ch) not in {("[", "]"), ("{", "}")}:
                    break
                if not stack:
                    yield text[start : idx + 1].strip()
                    break


def _response_json_candidates(response_text: str) -> List[str]:
    """Return JSON parse candidates in a forgiving, deterministic order."""
    candidates: List[str] = []
    stripped = response_text.strip()
    if stripped:
        candidates.append(stripped)

    for match in re.findall(r"```(?:json)?\s*([\s\S]*?)```", response_text, flags=re.IGNORECASE):
        snippet = match.strip()
        if snippet:
            candidates.append(snippet)

    candidates.extend(_balanced_json_snippets(response_text))

    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


def _unwrap_pattern_container(data: Any) -> Any:
    """Accept common wrapper objects around the pattern list."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return data

    for key in (
        "patterns",
        "pattern_records",
        "results",
        "items",
        "sequences",
        "パターン",
        "抽出パターン",
        "系列パターン",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return data


def _first_string(item: dict, keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _normalize_sequence(raw_sequence: Any) -> List[str]:
    """Normalize list or arrow-separated sequence text into state labels."""
    if isinstance(raw_sequence, list):
        return [str(part).strip() for part in raw_sequence if str(part).strip()]

    if isinstance(raw_sequence, str):
        text = raw_sequence.strip()
        if not text:
            return []

        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [str(part).strip() for part in decoded if str(part).strip()]

        parts = re.split(r"\s*(?:->|→|⇒|,|、|\||/|\n)\s*", text)
        return [part.strip() for part in parts if part.strip()]

    return []


def _normalize_adl_label_values(raw_labels: Any) -> List[str]:
    """Keep ADL interpretation labels as a string list if the LLM provided them."""
    if raw_labels is None:
        return []
    if isinstance(raw_labels, list):
        return [str(label).strip() for label in raw_labels if str(label).strip()]
    if isinstance(raw_labels, str):
        text = raw_labels.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [str(label).strip() for label in decoded if str(label).strip()]
        return [label.strip() for label in re.split(r"\s*(?:,|、|;|；|\||/|\n)\s*", text) if label.strip()]
    return []


def _normalize_pattern_records(data: Any) -> List[dict]:
    """Normalize parsed JSON data into the canonical pattern schema."""
    data = _unwrap_pattern_container(data)
    if not isinstance(data, list):
        return []

    extracted: List[dict] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue

        raw_sequence = None
        for key in (
            "遷移のパターン",
            "遷移のシーケンス",
            "sequence",
            "パターン",
            "系列",
            "states",
            "state_sequence",
        ):
            if key in item:
                raw_sequence = item[key]
                break

        sequence = _normalize_sequence(raw_sequence)
        if not sequence:
            continue

        pattern_name = _first_string(
            item,
            ("パターン名", "pattern_name", "name", "名称", "title"),
            default=f"Pattern {index}",
        )
        reason = _first_string(
            item,
            ("rationale", "解釈の根拠", "reason", "根拠", "explanation", "説明", "description"),
            default="",
        )
        raw_adl_labels = None
        for key in ("adl_sequence", "ADL系列ラベル", "adl_sequence_labels", "adl_labels", "ADLラベル"):
            if key in item:
                raw_adl_labels = item[key]
                break
        adl_labels = _normalize_adl_label_values(raw_adl_labels)

        record = {
            "パターン名": pattern_name,
            "解釈の根拠": reason,
            "遷移のパターン": sequence,
        }
        if adl_labels:
            record["ADL系列ラベル"] = adl_labels
        extracted.append(record)

    return extracted


def parse_pattern_records(response_text: str) -> List[dict]:
    """Normalize LLM response into a list of pattern records."""
    for candidate in _response_json_candidates(response_text):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        unwrapped = _unwrap_pattern_container(data)
        if isinstance(unwrapped, list) and not unwrapped:
            return []

        extracted = _normalize_pattern_records(data)
        if extracted:
            return extracted

    raise RuntimeError(
        "LLM応答をパターン配列として解釈できませんでした。"
        "JSON配列（例: [{\"パターン名\":\"...\",\"遷移のパターン\":[\"状態1\",\"状態2\"]}]）"
        "を返すようプロンプトを確認してください。"
    )


def extract_usage_from_response(response: object) -> dict:
    """Extract token usage metadata from a response object."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {
            "prompt_tokens": None,
            "response_tokens": None,
            "total_tokens": None,
        }

    prompt_tokens = getattr(usage, "prompt_token_count", None)
    if prompt_tokens is None:
        prompt_tokens = getattr(usage, "input_token_count", None)

    response_tokens = getattr(usage, "candidates_token_count", None)
    if response_tokens is None:
        response_tokens = getattr(usage, "output_token_count", None)

    total_tokens = getattr(usage, "total_token_count", None)
    if total_tokens is None and prompt_tokens is not None and response_tokens is not None:
        total_tokens = prompt_tokens + response_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }


def call_gemini(
    api_key: str,
    model_name: str,
    user_message: str,
    temperature: float,
) -> Tuple[str, str, dict, float]:
    """Call Gemini and return text, backend name, usage, and duration."""
    try:
        # Prefer the newer SDK if available.
        genai = importlib.import_module("google.genai")
        types = importlib.import_module("google.genai.types")

        def run_with_new_sdk() -> object:
            with genai.Client(api_key=api_key) as client:
                return client.models.generate_content(
                    model=model_name,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                    ),
                )

        start_time = time.monotonic()
        try:
            response = run_with_new_sdk()
        except RuntimeError as err:
            if "client has been closed" not in str(err).lower():
                raise
            response = run_with_new_sdk()
        duration_sec = time.monotonic() - start_time
        usage = extract_usage_from_response(response)

        text = getattr(response, "text", None)
        if text:
            return text, "google-genai", usage, duration_sec

        parts = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    parts.append(part_text)
        return "\n".join(parts).strip(), "google-genai", usage, duration_sec
    except ImportError:
        # Fallback to the legacy SDK.
        genai = importlib.import_module("google.generativeai")
        genai.configure(api_key=api_key)
        start_time = time.monotonic()
        response = genai.GenerativeModel(model_name=model_name).generate_content(
            user_message,
            generation_config={
                "temperature": temperature,
            },
        )
        duration_sec = time.monotonic() - start_time
        usage = extract_usage_from_response(response)
        return (getattr(response, "text", "") or "").strip(), "google-generativeai", usage, duration_sec


def extract_usage_from_bedrock_response(response: dict) -> dict:
    """Normalize Bedrock Converse usage to the existing metrics contract."""
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {
            "prompt_tokens": None,
            "response_tokens": None,
            "total_tokens": None,
        }

    prompt_tokens = usage.get("inputTokens")
    response_tokens = usage.get("outputTokens")
    total_tokens = usage.get("totalTokens")
    if total_tokens is None and prompt_tokens is not None and response_tokens is not None:
        total_tokens = prompt_tokens + response_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }


def _bedrock_error_message(exc: Exception, *, model_name: str, region_name: str) -> str:
    """Return an actionable message for common boto3/Bedrock failures."""
    exception_name = type(exc).__name__
    response = getattr(exc, "response", None)
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    error_code = str(error.get("Code") or exception_name)
    detail = str(error.get("Message") or exc)

    if exception_name in {"NoCredentialsError", "PartialCredentialsError"}:
        return (
            "AWS認証情報が見つからないか不完全です。aws configure、AWS_PROFILE、"
            "IAMロール等のAWS SDK標準credential chainを設定してください。"
        )
    if error_code in {"AccessDeniedException", "UnauthorizedException", "UnrecognizedClientException"}:
        return (
            f"Amazon Bedrockへのアクセスが拒否されました（{error_code}）。"
            "bedrock:InvokeModel権限、モデルアクセス、AWSアカウント/プロファイルを確認してください。"
            f" modelId={model_name}, region={region_name}: {detail}"
        )
    if error_code in {"ResourceNotFoundException", "ModelNotReadyException"}:
        return (
            f"Bedrock modelIdを利用できません（{error_code}）。"
            f"modelIdとリージョンを確認してください: modelId={model_name}, "
            f"region={region_name}: {detail}"
        )
    if error_code == "ValidationException":
        return (
            "Bedrockリクエストが拒否されました（ValidationException）。"
            "modelIdがConverse API対応か、指定リージョンで利用可能か、"
            f"推論設定がモデル要件に合うか確認してください: modelId={model_name}, "
            f"region={region_name}: {detail}"
        )
    if exception_name == "ReadTimeoutError":
        return (
            "Bedrock Runtimeからの応答待ちがread timeoutを超えました。"
            "モデルが推論を完了している可能性もあるため、同じリクエストを無制限に再送しません。"
            "BEDROCK_READ_TIMEOUT_SECONDS、入力サイズ、Bedrock側の一時的な遅延を確認してください: "
            f"region={region_name}: {detail}"
        )
    if exception_name in {
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "UnknownEndpointError",
    }:
        return (
            "Bedrock Runtimeエンドポイントへ接続できません。"
            f"AWS_REGIONとネットワークを確認してください: region={region_name}: {detail}"
        )
    return (
        f"Bedrock Converse APIリクエストに失敗しました（{error_code}）。"
        f"modelId={model_name}, region={region_name}: {detail}"
    )


def _bedrock_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    return str(error.get("Code") or type(exc).__name__)


def is_fable_data_retention_routing_error(exc: Exception, model_name: str) -> bool:
    """Return whether a Fable profile was rejected before inference for retention mode.

    Cross-Region profiles can briefly route to a destination where a newly
    enabled account retention setting has not propagated yet. The request is
    rejected before inference, so retrying does not create a duplicate output.
    """
    normalized_model_name = model_name.strip().lower()
    if normalized_model_name not in {
        "anthropic.claude-fable-5",
        "global.anthropic.claude-fable-5",
        "us.anthropic.claude-fable-5",
    }:
        return False
    return (
        _bedrock_error_code(exc) == "ValidationException"
        and "data retention mode" in str(exc).lower()
        and "not available for this model" in str(exc).lower()
    )


def build_bedrock_messages(user_message: str) -> List[dict]:
    """Build the single source of truth for Converse and CountTokens messages."""
    return [
        {
            "role": "user",
            "content": [{"text": user_message}],
        }
    ]


def approximate_bedrock_input_tokens(messages: Sequence[dict]) -> int:
    """Return a deliberately conservative fallback based on UTF-8 payload bytes.

    Model tokenizers generally combine bytes into tokens. Counting 110% of the
    serialized UTF-8 bytes plus framing headroom therefore favors overestimation,
    including for Japanese text, while remaining deterministic and dependency-free.
    """
    serialized = json.dumps(
        {"messages": list(messages)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return max(1, math.ceil(len(serialized) * 1.10) + 32)


def _bedrock_failure_summary(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    code = str(error.get("Code") or type(exc).__name__)
    detail = str(error.get("Message") or exc)
    return f"{code}: {detail}"


def count_bedrock_input_tokens(
    *,
    model_name: str,
    user_messages: Sequence[str],
    region_name: str,
) -> BedrockInputTokenCount:
    """Count planned Bedrock inputs, falling back without invoking the model.

    Once CountTokens fails, the remaining requests use the conservative fallback
    to avoid repeated unsupported calls for inference-profile model IDs.
    """
    # CountTokens is deterministic for an identical model/input pair.  Collapse
    # exact duplicate prompts (typically repeated experimental runs) while still
    # counting every distinct prompt independently.
    grouped_messages: dict[str, tuple[List[dict], int]] = {}
    for user_message in user_messages:
        existing = grouped_messages.get(user_message)
        if existing is None:
            grouped_messages[user_message] = (build_bedrock_messages(user_message), 1)
        else:
            grouped_messages[user_message] = (existing[0], existing[1] + 1)
    if not grouped_messages:
        return BedrockInputTokenCount(
            total_tokens=0,
            exact=True,
            method="No requests",
        )

    try:
        client = create_bedrock_runtime_client(region_name)
    except Exception as exc:
        total = sum(
            approximate_bedrock_input_tokens(messages) * repetitions
            for messages, repetitions in grouped_messages.values()
        )
        return BedrockInputTokenCount(
            total_tokens=total,
            exact=False,
            method="approximate fallback (conservative UTF-8 byte estimate)",
            warning=f"Bedrock CountTokens client was unavailable; fallback used. {_bedrock_failure_summary(exc)}",
        )

    total_tokens = 0
    count_tokens_available = True
    exact_groups_counted = 0
    failure_reason: Optional[str] = None
    for messages, repetitions in grouped_messages.values():
        if count_tokens_available:
            try:
                response = client.count_tokens(
                    modelId=model_name,
                    input={"converse": {"messages": messages}},
                )
                input_tokens = response.get("inputTokens") if isinstance(response, dict) else None
                if not isinstance(input_tokens, int) or input_tokens < 0:
                    raise RuntimeError("response did not contain a non-negative inputTokens integer")
                total_tokens += input_tokens * repetitions
                exact_groups_counted += 1
                continue
            except Exception as exc:
                count_tokens_available = False
                failure_reason = _bedrock_failure_summary(exc)
        total_tokens += approximate_bedrock_input_tokens(messages) * repetitions

    if count_tokens_available:
        return BedrockInputTokenCount(
            total_tokens=total_tokens,
            exact=True,
            method="Bedrock CountTokens",
        )
    method = "approximate fallback (conservative UTF-8 byte estimate)"
    if exact_groups_counted:
        method = "Bedrock CountTokens + approximate fallback"
    return BedrockInputTokenCount(
        total_tokens=total_tokens,
        exact=False,
        method=method,
        warning=f"Bedrock CountTokens was unavailable; fallback used. {failure_reason}",
    )


def call_bedrock(
    *,
    model_name: str,
    user_message: str,
    temperature: Optional[float],
    region_name: str,
    max_tokens: int,
) -> Tuple[str, str, dict, float]:
    """Call Amazon Bedrock Converse and return the shared response tuple."""
    try:
        client = create_bedrock_runtime_client(region_name)
        messages = build_bedrock_messages(user_message)
        inference_config: dict[str, int | float] = {"maxTokens": max_tokens}
        # GPT-5.6 profiles and Claude Fable 5 reject arbitrary ``temperature``.
        # Leave it to the service default for those models while retaining the
        # common Converse parameter for models that support it.
        if temperature is not None and bedrock_supports_temperature(model_name):
            inference_config["temperature"] = temperature
        for attempt in range(1, FABLE_DATA_RETENTION_MAX_ATTEMPTS + 1):
            start_time = time.monotonic()
            try:
                response = client.converse(
                    modelId=model_name,
                    messages=messages,
                    inferenceConfig=inference_config,
                )
                duration_sec = time.monotonic() - start_time
                break
            except Exception as exc:
                retention_routing_error = is_fable_data_retention_routing_error(
                    exc, model_name
                )
                # This validation rejection occurs before inference on the
                # cross-region Fable profile.  It is the sole explicit retry
                # here; ordinary transport retries belong to Botocore Config.
                if retention_routing_error and attempt < FABLE_DATA_RETENTION_MAX_ATTEMPTS:
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise
    except Exception as exc:
        raise RuntimeError(
            _bedrock_error_message(exc, model_name=model_name, region_name=region_name)
        ) from exc

    if not isinstance(response, dict):
        raise RuntimeError(
            "Bedrock Converse APIのレスポンスが想定形式（dict）ではありません。"
        )

    output = response.get("output")
    message = output.get("message") if isinstance(output, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        raise RuntimeError(
            "Bedrock Converse APIレスポンスに output.message.content がありません。"
        )

    text_parts = [
        item["text"]
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"]
    ]
    if not text_parts:
        raise RuntimeError(
            "Bedrock Converse APIレスポンスにテキスト本文がありません。"
        )

    usage = extract_usage_from_bedrock_response(response)
    return "\n".join(text_parts).strip(), "aws-bedrock-converse", usage, duration_sec


def call_llm(config: LLMRuntimeConfig, user_message: str) -> Tuple[str, str, dict, float]:
    """Dispatch one request while preserving the historical response tuple."""
    if config.provider == "google_gemini":
        return call_gemini(
            api_key=config.api_key or "",
            model_name=config.model_name,
            user_message=user_message,
            temperature=config.temperature,
        )
    if config.provider == "bedrock":
        return call_bedrock(
            model_name=config.model_name,
            user_message=user_message,
            temperature=config.temperature,
            region_name=config.region_name or "",
            max_tokens=config.max_tokens or 0,
        )
    raise RuntimeError(f"未対応のLLM providerです: {config.provider}")
