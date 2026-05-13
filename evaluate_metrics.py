"""
ベースライン系列とLLM系列を比較し、Precision / Recall / F1 を評価するスクリプト。

実行方法:
    uv run evaluate_metrics.py

入力ファイル（状態名のリストのリスト）:
    - output/baseline_sequences.json
    - output/llm_sequences.json

出力:
    Precision: TP / (TP + FP) LLMが提案したシーケンスが、実際のデータ（ベースライン）に本当に存在し、かつ統計的に有意か
    Recall: TP / (TP + FN) ベースラインが見つけた「明らかに頻出するシーケンス」を、LLMがちゃんと拾い上げているか
    F1-score: 2 * Precision * Recall / (Precision + Recall)
    TP: LLMが生成したシーケンスのうち、ベースラインにも存在するもの
    FP: LLMが生成したシーケンスのうち、ベースラインに存在しないもの
    FN: ベースラインに存在するシーケンスのうち、LLMが生成しなかったもの
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
BASELINE_PATH = Path("output/prob_threshold_sequences.json")
STATE_COUNT_BASELINE_PATH = Path("output/state_sequence_counts.json")
LLM_PATH = Path("output/llm_sequences.json")
LLM_MODES_PATH = Path("output/llm_sequences_modes.json")
OUTPUT_REPORT_PATH = Path("output/evaluation_report.txt")

# True: ベースラインがLLMを包含する場合もマッチとみなす
# 例 LLM=[B,C], BASE=[A,B,C] -> True のときマッチ
ALLOW_BASELINE_CONTAINS_LLM = False

# True: LLMがベースラインを包含する場合もマッチとみなす
# 例 LLM=[A,B,C], BASE=[B,C] -> True のときマッチ
ALLOW_LLM_CONTAINS_BASELINE = False


@dataclass(frozen=True)
class EvaluationResult:
    """評価結果をまとめるデータ構造。"""

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
    """JSONファイルからシーケンス配列を読み込む。

    対応形式:
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
        # 形式1: 2次元配列
        if isinstance(item, list):
            if not all(isinstance(x, str) for x in item):
                raise ValueError(f"不正なシーケンス形式です: index={i}, path={path}")
            normalized.append(item)
            continue

        # 形式2: オブジェクト配列（パターン名は無視し、遷移のシーケンスのみ使用）
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
    """state_sequence_counts.json 形式（[{..., sequence:[...], ...}, ...]）を読み込む。"""
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
    """shorter が longer の連続部分列かどうかを判定する。"""
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
    """一致・包含ルールに基づいて2系列がマッチするか判定する。"""
    if list(seq_llm) == list(seq_base):
        return True

    # LLMがベースラインを包含（LLMの中にベースラインが連続部分列として存在）
    if allow_llm_contains_base and is_contiguous_subsequence(seq_base, seq_llm):
        return True

    # ベースラインがLLMを包含（オプション）
    if allow_base_contains_llm and is_contiguous_subsequence(seq_llm, seq_base):
        return True

    return False


def compute_metrics(
    baseline_results: Sequence[Sequence[str]],
    llm_results: Sequence[Sequence[str]],
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> EvaluationResult:
    """TP/FP/FNを1対1対応で集計し、Precision/Recall/F1を計算する。"""
    tp_items: List[Tuple[List[str], List[int]]] = []
    fp_items: List[List[str]] = []

    # 1対1対応: 1つのbaselineは最大1つのLLM系列にのみ対応させる。
    # これにより TP+FN=|baseline|, TP+FP=|llm| が常に成り立つ。
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
    """シーケンスを見やすい文字列へ整形する。"""
    return " -> ".join(seq)


def print_report(
    baseline_results: Sequence[Sequence[str]],
    llm_results: Sequence[Sequence[str]],
    result: EvaluationResult,
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> None:
    """評価結果を標準出力にわかりやすく表示する。"""
    print(
        build_report_text(
            baseline_results,
            llm_results,
            result,
            allow_base_contains_llm,
            allow_llm_contains_base,
        )
    )


def build_report_text(
    baseline_results: Sequence[Sequence[str]],
    llm_results: Sequence[Sequence[str]],
    result: EvaluationResult,
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> str:
    """評価レポート文字列を生成する。"""
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


def build_quad_report_text(
    llm_results: Sequence[Sequence[str]],
    llm_modes_results: Sequence[Sequence[str]],
    prob_baseline_results: Sequence[Sequence[str]],
    state_count_baseline_results: Sequence[Sequence[str]],
    llm_vs_prob_result: EvaluationResult,
    llm_vs_state_count_result: EvaluationResult,
    llm_modes_vs_prob_result: EvaluationResult,
    llm_modes_vs_state_count_result: EvaluationResult,
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> str:
    """4つの比較結果を1つのレポートにまとめる。"""
    lines: List[str] = []

    def matched_ranks_from_result(result: EvaluationResult) -> List[int]:
        """TPでヒットした baseline index を rank(1始まり) に変換して返す。"""
        matched_indices = {
            idx
            for _, matched_list in result.tp_items
            for idx in matched_list
        }
        return [idx + 1 for idx in sorted(matched_indices)]

    lines.append("# 1) LLM vs 遷移確率ベースライン")
    lines.append(
        build_report_text(
            baseline_results=prob_baseline_results,
            llm_results=llm_results,
            result=llm_vs_prob_result,
            allow_base_contains_llm=allow_base_contains_llm,
            allow_llm_contains_base=allow_llm_contains_base,
        )
    )

    lines.append("\n# 2) LLM vs state_sequence_counts ベースライン")
    lines.append(
        build_report_text(
            baseline_results=state_count_baseline_results,
            llm_results=llm_results,
            result=llm_vs_state_count_result,
            allow_base_contains_llm=allow_base_contains_llm,
            allow_llm_contains_base=allow_llm_contains_base,
        )
    )
    matched_ranks = matched_ranks_from_result(llm_vs_state_count_result)
    lines.append(
        f"[state_sequence_countsでLLMが出力できたrank一覧: {len(matched_ranks)}件] "
        f"{matched_ranks}"
    )

    lines.append("\n# 3) LLM_modes vs 遷移確率ベースライン")
    lines.append(
        build_report_text(
            baseline_results=prob_baseline_results,
            llm_results=llm_modes_results,
            result=llm_modes_vs_prob_result,
            allow_base_contains_llm=allow_base_contains_llm,
            allow_llm_contains_base=allow_llm_contains_base,
        )
    )

    lines.append("\n# 4) LLM_modes vs state_sequence_counts ベースライン")
    lines.append(
        build_report_text(
            baseline_results=state_count_baseline_results,
            llm_results=llm_modes_results,
            result=llm_modes_vs_state_count_result,
            allow_base_contains_llm=allow_base_contains_llm,
            allow_llm_contains_base=allow_llm_contains_base,
        )
    )
    matched_ranks_modes = matched_ranks_from_result(llm_modes_vs_state_count_result)
    lines.append(
        f"[state_sequence_countsでLLM_modesが出力できたrank一覧: {len(matched_ranks_modes)}件] "
        f"{matched_ranks_modes}"
    )

    return "\n".join(lines)


def save_report(report_text: str, output_path: Path) -> None:
    """評価レポートを output フォルダに保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text + "\n", encoding="utf-8")


def main() -> None:
    """評価スクリプトのエントリーポイント。"""
    prob_baseline_results = load_sequences(BASELINE_PATH)
    state_count_baseline_results = load_sequences_from_state_count_json(STATE_COUNT_BASELINE_PATH)
    llm_results = load_sequences(LLM_PATH)
    llm_modes_results = load_sequences(LLM_MODES_PATH)

    llm_vs_prob_result = compute_metrics(
        baseline_results=prob_baseline_results,
        llm_results=llm_results,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    llm_vs_state_count_result = compute_metrics(
        baseline_results=state_count_baseline_results,
        llm_results=llm_results,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    llm_modes_vs_prob_result = compute_metrics(
        baseline_results=prob_baseline_results,
        llm_results=llm_modes_results,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    llm_modes_vs_state_count_result = compute_metrics(
        baseline_results=state_count_baseline_results,
        llm_results=llm_modes_results,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )

    report_text = build_quad_report_text(
        llm_results=llm_results,
        llm_modes_results=llm_modes_results,
        prob_baseline_results=prob_baseline_results,
        state_count_baseline_results=state_count_baseline_results,
        llm_vs_prob_result=llm_vs_prob_result,
        llm_vs_state_count_result=llm_vs_state_count_result,
        llm_modes_vs_prob_result=llm_modes_vs_prob_result,
        llm_modes_vs_state_count_result=llm_modes_vs_state_count_result,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    save_report(report_text, OUTPUT_REPORT_PATH)
    print(report_text)
    print(f"\nレポート保存先: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
