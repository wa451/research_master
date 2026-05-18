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

from pathlib import Path
from typing import List, Sequence

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR
from utils.eval_utils import (
    EvaluationResult,
    build_report_text,
    compute_metrics,
    format_seq,
    is_contiguous_subsequence,
    is_match,
    load_sequences,
    load_sequences_from_state_count_json,
)


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
# パラメータに基づく出力フォルダ
OUTPUT_DIR = ROOT_DIR / "output" / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
PARAM_SUFFIX = f"{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"

BASELINE_PATH = OUTPUT_DIR / f"prob_threshold_sequences_{PARAM_SUFFIX}.json"
STATE_COUNT_BASELINE_PATH = OUTPUT_DIR / f"state_sequence_counts_{PARAM_SUFFIX}.json"
LLM_MODES_PATH = OUTPUT_DIR / f"llm_sequences_modes_{PARAM_SUFFIX}.json"
OUTPUT_REPORT_PATH = OUTPUT_DIR / f"evaluation_report_{PARAM_SUFFIX}.txt"

# True: ベースラインがLLMを包含する場合もマッチとみなす
# 例 LLM=[B,C], BASE=[A,B,C] -> True のときマッチ
ALLOW_BASELINE_CONTAINS_LLM = False

# True: LLMがベースラインを包含する場合もマッチとみなす
# 例 LLM=[A,B,C], BASE=[B,C] -> True のときマッチ
ALLOW_LLM_CONTAINS_BASELINE = False


def build_report_text_modes(
    llm_modes_results: Sequence[Sequence[str]],
    prob_baseline_results: Sequence[Sequence[str]],
    state_count_baseline_results: Sequence[Sequence[str]],
    llm_modes_vs_prob_result: EvaluationResult,
    llm_modes_vs_state_count_result: EvaluationResult,
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> str:
    """modes版LLMの2つの比較結果をまとめる。"""
    lines: List[str] = []

    def matched_ranks_from_result(result: EvaluationResult) -> List[int]:
        """TPでヒットした baseline index を rank(1始まり) に変換して返す。"""
        matched_indices = {
            idx
            for _, matched_list in result.tp_items
            for idx in matched_list
        }
        return [idx + 1 for idx in sorted(matched_indices)]

    lines.append("# 1) LLM_modes vs 遷移確率ベースライン")
    lines.append(
        build_report_text(
            baseline_results=prob_baseline_results,
            llm_results=llm_modes_results,
            result=llm_modes_vs_prob_result,
            allow_base_contains_llm=allow_base_contains_llm,
            allow_llm_contains_base=allow_llm_contains_base,
        )
    )

    lines.append("\n# 2) LLM_modes vs state_sequence_counts ベースライン")
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


def main(
    llm_modes_path: Path,
    report_path: Path,
) -> tuple[EvaluationResult, EvaluationResult]:
    """評価を実行し、両ベースラインに対する結果を返す。
    
    Args:
        llm_modes_path: LLM出力ファイルパス
        report_path: レポート出力パス
    
    戻り値: (prob_baseline_result, state_count_baseline_result)
    """
    prob_baseline_results = load_sequences(BASELINE_PATH)
    state_count_baseline_results = load_sequences_from_state_count_json(STATE_COUNT_BASELINE_PATH)
    llm_modes_results = load_sequences(llm_modes_path)

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

    report_text = build_report_text_modes(
        llm_modes_results=llm_modes_results,
        prob_baseline_results=prob_baseline_results,
        state_count_baseline_results=state_count_baseline_results,
        llm_modes_vs_prob_result=llm_modes_vs_prob_result,
        llm_modes_vs_state_count_result=llm_modes_vs_state_count_result,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    save_report(report_text, report_path)
    
    return llm_modes_vs_prob_result, llm_modes_vs_state_count_result


if __name__ == "__main__":
    RUNS = 5
    for run_idx in range(1, RUNS + 1):
        print(f"\n=== Run {run_idx} ===")
        llm_output_path = OUTPUT_DIR / f"llm_sequences_modes_{PARAM_SUFFIX}_{run_idx}.json"
        report_path = OUTPUT_DIR / f"evaluation_report_{PARAM_SUFFIX}_{run_idx}.txt"
        prob_result, state_result = main(llm_output_path, report_path)
    print(f"レポート保存先: {OUTPUT_REPORT_PATH}")
