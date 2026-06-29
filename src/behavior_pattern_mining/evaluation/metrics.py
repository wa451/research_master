"""Shared evaluation helpers for sequence metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class EvaluationResult:
    """Evaluation metrics and matched items."""

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    tp_items: List[Tuple[List[str], List[int]]]
    fp_items: List[List[str]]
    fn_items: List[List[str]]


def load_sequences(path: Path) -> List[List[str]]:
    """Load sequences from a JSON list.

    Supported formats:
    1) [["状態1", "状態2"], ...]
    2) [{"パターン名": "...", "遷移のシーケンス": ["状態1", ...]}, ...]
    """
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"不正な形式です（配列が必要）: {path}")

    normalized: List[List[str]] = []
    for i, item in enumerate(payload):
        if isinstance(item, list):
            if not all(isinstance(x, str) for x in item):
                raise ValueError(f"不正なシーケンス形式です: index={i}, path={path}")
            normalized.append(item)
            continue

        if isinstance(item, dict):
            seq = item.get("遷移のシーケンス")
            if seq is None:
                seq = item.get("sequence")
            if not isinstance(seq, list) or not all(isinstance(x, str) for x in seq):
                raise ValueError(f"不正なシーケンス形式です: index={i}, path={path}")
            normalized.append(seq)
            continue

        raise ValueError(f"不正な要素形式です: index={i}, path={path}")
    return normalized


def load_sequences_from_state_count_json(path: Path) -> List[List[str]]:
    """Load sequences from state_sequence_counts.json format."""
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"不正な形式です（配列が必要）: {path}")

    normalized: List[List[str]] = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"不正な要素形式です（objectが必要）: index={i}, path={path}")
        seq = item.get("sequence")
        if not isinstance(seq, list) or not all(isinstance(x, str) for x in seq):
            raise ValueError(f"sequence が不正です: index={i}, path={path}")
        normalized.append(seq)

    return normalized


def is_contiguous_subsequence(shorter: Sequence[str], longer: Sequence[str]) -> bool:
    """Return True if shorter is a contiguous subsequence of longer."""
    n, m = len(shorter), len(longer)
    if n == 0 or n > m:
        return False
    for start in range(m - n + 1):
        if list(longer[start : start + n]) == list(shorter):
            return True
    return False


def is_match(
    seq_llm: Sequence[str],
    seq_base: Sequence[str],
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> bool:
    """Return True if two sequences match under containment rules."""
    if list(seq_llm) == list(seq_base):
        return True

    if allow_llm_contains_base and is_contiguous_subsequence(seq_base, seq_llm):
        return True

    if allow_base_contains_llm and is_contiguous_subsequence(seq_llm, seq_base):
        return True

    return False


def compute_metrics(
    baseline_results: Sequence[Sequence[str]],
    llm_results: Sequence[Sequence[str]],
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> EvaluationResult:
    """Compute TP/FP/FN, precision/recall/f1 with one-to-one matching."""
    tp_items: List[Tuple[List[str], List[int]]] = []
    fp_items: List[List[str]] = []

    unmatched_base_indices = set(range(len(baseline_results)))

    for llm_seq in llm_results:
        matched_base_indices = [
            idx
            for idx in sorted(unmatched_base_indices)
            for base_seq in [baseline_results[idx]]
            if is_match(
                llm_seq,
                base_seq,
                allow_base_contains_llm=allow_base_contains_llm,
                allow_llm_contains_base=allow_llm_contains_base,
            )
        ]

        if matched_base_indices:
            chosen_idx = matched_base_indices[0]
            tp_items.append((list(llm_seq), [chosen_idx]))
            unmatched_base_indices.remove(chosen_idx)
        else:
            fp_items.append(list(llm_seq))

    fn_items = [list(baseline_results[i]) for i in sorted(unmatched_base_indices)]

    tp = len(tp_items)
    fp = len(fp_items)
    fn = len(fn_items)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return EvaluationResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        tp_items=tp_items,
        fp_items=fp_items,
        fn_items=fn_items,
    )


def format_seq(seq: Sequence[str]) -> str:
    """Format a sequence for display."""
    return " -> ".join(seq)


def build_report_text(
    baseline_results: Sequence[Sequence[str]],
    llm_results: Sequence[Sequence[str]],
    result: EvaluationResult,
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> str:
    """Build a human-readable evaluation report text."""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append("シーケンス評価レポート")
    lines.append("=" * 80)
    lines.append(f"ベースライン系列数                 : {len(baseline_results)}")
    lines.append(f"LLM系列数                          : {len(llm_results)}")
    lines.append(f"ベースラインがLLMを包含を許可      : {allow_base_contains_llm}")
    lines.append(f"LLMがベースラインを包含を許可      : {allow_llm_contains_base}")
    lines.append("-" * 80)
    lines.append(f"TP                                 : {result.tp}")
    lines.append(f"FP                                 : {result.fp}")
    lines.append(f"FN                                 : {result.fn}")
    lines.append(f"Precision                          : {result.precision:.3f}")
    lines.append(f"Recall                             : {result.recall:.3f}")
    lines.append(f"F1-score                           : {result.f1:.3f}")
    lines.append("=" * 80)

    lines.append(f"[TP一覧: {len(result.tp_items)}件] LLM系列 と マッチした baseline index")
    if not result.tp_items:
        lines.append("  なし")
    for seq, matched_indices in result.tp_items:
        lines.append(f"  - {format_seq(seq)}")
        lines.append(f"    matched_baseline_indices: {matched_indices}")

    lines.append(f"[FP一覧: {len(result.fp_items)}件] LLM系列でマッチしなかったもの")
    if not result.fp_items:
        lines.append("  なし")
    for seq in result.fp_items:
        lines.append(f"  - {format_seq(seq)}")

    lines.append(f"[FN一覧: {len(result.fn_items)}件] baseline系列でカバーされなかったもの")
    if not result.fn_items:
        lines.append("  なし")
    for seq in result.fn_items:
        lines.append(f"  - {format_seq(seq)}")

    return "\n".join(lines)
