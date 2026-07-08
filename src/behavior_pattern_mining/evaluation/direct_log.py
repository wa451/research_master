"""
直接ログベースのLLM抽出結果を評価するスクリプト。
ベースライン系列とLLM系列を比較し、Precision / Recall / F1 を計算します。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from openpyxl import Workbook

from experiment_config import (
    ALLOW_BASELINE_CONTAINS_LLM as CONFIG_ALLOW_BASELINE_CONTAINS_LLM,
    ALLOW_LLM_CONTAINS_BASELINE as CONFIG_ALLOW_LLM_CONTAINS_BASELINE,
    DATASET_NAME,
    DAYS,
    ROOT_DIR,
    HAMMING_THRESHOLD,
)
from src.behavior_pattern_mining.evaluation.metrics import (
    EvaluationResult,
    build_report_text,
    compute_metrics,
    load_sequences,
    load_sequences_from_state_count_json,
)


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
# 確率ベースラインの出力ファイルパス
BASELINE_PROB_PATH = Path(
    ROOT_DIR
    / "output"
    / f"{DATASET_NAME}_{15}_{HAMMING_THRESHOLD}_{DAYS}days"
    / f"prob_threshold_sequences_{15}_{HAMMING_THRESHOLD}_{DAYS}days.json"
)
# 頻度ベースラインの出力ファイルパス
BASELINE_COUNT_PATH = Path(
    ROOT_DIR
    / "output"
    / f"{DATASET_NAME}_{15}_{1}_{DAYS}days"
    / f"state_sequence_counts_{15}_{1}_{DAYS}days.json"
)
# 直接ログベースのLLM抽出結果（複数run）
DIRECT_LOG_OUTPUT_DIR = ROOT_DIR / "output" / f"llm_direct_{DAYS}"

# True: ベースラインがLLMを包含する場合もマッチとみなす
ALLOW_BASELINE_CONTAINS_LLM = CONFIG_ALLOW_BASELINE_CONTAINS_LLM

# True: LLMがベースラインを包含する場合もマッチとみなす
ALLOW_LLM_CONTAINS_BASELINE = CONFIG_ALLOW_LLM_CONTAINS_BASELINE


@dataclass(frozen=True)
class RunMetricSummary:
    """runごとの主要評価指標を保持する。"""

    run_idx: int
    prob_precision: float
    prob_recall: float
    prob_f1: float
    count_precision: float
    count_recall: float
    count_f1: float


def build_report_text_direct(
    baseline_results: Sequence[Sequence[str]],
    llm_results: Sequence[Sequence[str]],
    result: EvaluationResult,
    allow_base_contains_llm: bool,
    allow_llm_contains_base: bool,
) -> str:
    """評価レポート文字列を生成する（直接ログ用）。"""
    report_text = build_report_text(
        baseline_results,
        llm_results,
        result,
        allow_base_contains_llm,
        allow_llm_contains_base,
    )
    return report_text.replace("パターン評価レポート", "パターン評価レポート（直接ログ）", 1)


def evaluate_run(run_idx: int) -> Optional[Tuple[str, RunMetricSummary]]:
    """1つの run について評価を実行し、結果を表示する。"""
    llm_run_path = DIRECT_LOG_OUTPUT_DIR / f"{run_idx}.json"
    if not llm_run_path.exists():
        print(f"Run {run_idx}: LLMファイルが見つかりません -> {llm_run_path}")
        return None

    baseline_prob = load_sequences(BASELINE_PROB_PATH)
    baseline_count = load_sequences_from_state_count_json(BASELINE_COUNT_PATH)

    llm_sequences = load_sequences(llm_run_path)

    print(f"\n=== Run {run_idx}: 確率ベースラインとの比較 ===")
    result_prob = compute_metrics(
        baseline_prob,
        llm_sequences,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    report_prob_text = build_report_text_direct(
        baseline_prob,
        llm_sequences,
        result_prob,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    print(report_prob_text)

    print(f"\n=== Run {run_idx}: 頻度ベースラインとの比較 ===")
    result_count = compute_metrics(
        baseline_count,
        llm_sequences,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    report_count_text = build_report_text_direct(
        baseline_count,
        llm_sequences,
        result_count,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    print(report_count_text)

    report_text = "\n\n".join(
        [
            f"=== Run {run_idx}: 確率ベースラインとの比較 ===\n{report_prob_text}",
            f"=== Run {run_idx}: 頻度ベースラインとの比較 ===\n{report_count_text}",
        ]
    )
    summary = RunMetricSummary(
        run_idx=run_idx,
        prob_precision=result_prob.precision,
        prob_recall=result_prob.recall,
        prob_f1=result_prob.f1,
        count_precision=result_count.precision,
        count_recall=result_count.recall,
        count_f1=result_count.f1,
    )
    return report_text, summary


def save_metrics_excel(summaries: List[RunMetricSummary], output_path: Path) -> None:
    """runごとのPrecision/Recall/F1を1つのExcelに保存する。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "metrics"

    headers = [
        "run",
        "prob_precision",
        "prob_recall",
        "prob_f1",
        "count_precision",
        "count_recall",
        "count_f1",
    ]
    ws.append(headers)

    for s in sorted(summaries, key=lambda x: x.run_idx):
        ws.append(
            [
                s.run_idx,
                s.prob_precision,
                s.prob_recall,
                s.prob_f1,
                s.count_precision,
                s.count_recall,
                s.count_f1,
            ]
        )

    wb.save(output_path)


def main() -> None:
    """全runについて評価を実行する。"""
    if not DIRECT_LOG_OUTPUT_DIR.exists():
        raise FileNotFoundError(f"出力ディレクトリが見つかりません: {DIRECT_LOG_OUTPUT_DIR}")

    run_files = sorted(DIRECT_LOG_OUTPUT_DIR.glob("*.json"))
    if not run_files:
        print(f"出力ファイルが見つかりません: {DIRECT_LOG_OUTPUT_DIR}")
        return

    all_run_reports: List[str] = []
    run_metric_summaries: List[RunMetricSummary] = []
    for run_path in run_files:
        try:
            run_idx = int(run_path.stem)
            run_result = evaluate_run(run_idx)
            if run_result:
                run_report, run_summary = run_result
                all_run_reports.append(run_report)
                run_metric_summaries.append(run_summary)
        except ValueError:
            continue

    if all_run_reports:
        report_output_path = DIRECT_LOG_OUTPUT_DIR / "evaluate_direct_log_report.txt"
        report_output_path.write_text(
            "\n\n".join(all_run_reports),
            encoding="utf-8",
        )
        print(f"\n評価レポートを保存しました: {report_output_path}")

    if run_metric_summaries:
        excel_output_path = DIRECT_LOG_OUTPUT_DIR / f"evaluate_direct_log_metrics_{DAYS}days.xlsx"
        save_metrics_excel(run_metric_summaries, excel_output_path)
        print(f"評価指標Excelを保存しました: {excel_output_path}")


if __name__ == "__main__":
    main()
