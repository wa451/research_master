"""Shared helpers for LLM extraction scripts."""

from __future__ import annotations

import importlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, List, Tuple


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
            ("解釈の根拠", "reason", "根拠", "explanation", "説明", "description"),
            default="",
        )
        raw_adl_labels = None
        for key in ("ADL系列ラベル", "adl_sequence_labels", "adl_labels", "ADLラベル"):
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
