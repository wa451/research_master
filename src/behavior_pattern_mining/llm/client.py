"""Shared helpers for LLM extraction scripts."""

from __future__ import annotations

import importlib
import json
import os
import re
import time
from pathlib import Path
from typing import List, Tuple


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


def parse_pattern_records(response_text: str) -> List[dict]:
    """Normalize LLM response into a list of pattern records."""
    candidates = [response_text.strip()]

    for match in re.findall(r"```(?:json)?\s*([\s\S]*?)```", response_text, flags=re.IGNORECASE):
        candidates.append(match.strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            extracted: List[dict] = []
            for item in data:
                seq = item.get("遷移のシーケンス")
                if seq is None:
                    seq = item.get("sequence")
                if not isinstance(seq, list) or not all(isinstance(s, str) for s in seq):
                    extracted = []
                    break

                pattern_name = item.get("パターン名")
                if not isinstance(pattern_name, str) or not pattern_name.strip():
                    extracted = []
                    break

                reason = item.get("解釈の根拠")
                if reason is None:
                    reason = item.get("reason")
                if not isinstance(reason, str):
                    reason = ""

                extracted.append(
                    {
                        "パターン名": pattern_name.strip(),
                        "解釈の根拠": reason.strip(),
                        "遷移のシーケンス": seq,
                    }
                )
            if extracted:
                return extracted

    raise RuntimeError(
        "LLM応答をパターン配列として解釈できませんでした。"
        "JSON配列（例: [{\"パターン名\":\"...\",\"遷移のシーケンス\":[\"状態1\",\"状態2\"]}]）"
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
