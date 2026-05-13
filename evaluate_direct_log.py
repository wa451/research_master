"""
直接ログベースのLLM抽出結果を評価するスクリプト。
ベースライン系列とLLM系列を比較し、Precision / Recall / F1 を計算します。

evaluate_metrics.py と同じロジックを使用。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from openpyxl import Workbook

from experiment_config import DATASET_NAME, DAYS, ROOT_DIR, HAMMING_THRESHOLD


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
ALLOW_BASELINE_CONTAINS_LLM = False

# True: LLMがベースラインを包含する場合もマッチとみなす
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
    lines.append("シーケンス評価レポート（直接ログ）")
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


def evaluate_run(run_idx: int) -> Optional[Tuple[str, RunMetricSummary]]:
    """1つの run について評価を実行し、結果を表示する。"""
    # 直接ログベースのLLM出力（各run）
    llm_run_path = DIRECT_LOG_OUTPUT_DIR / f"{run_idx}.json"
    if not llm_run_path.exists():
        print(f"Run {run_idx}: LLMファイルが見つかりません -> {llm_run_path}")
        return None

    # ベースラインを読み込み
    baseline_prob = load_sequences(BASELINE_PROB_PATH)
    baseline_count = load_sequences_from_state_count_json(BASELINE_COUNT_PATH)

    # LLM出力を読み込み
    llm_sequences = load_sequences(llm_run_path)

    # 確率ベースラインで評価
    print(f"\n=== Run {run_idx}: 確率ベースラインとの比較 ===")
    result_prob = compute_metrics(
        baseline_prob,
        llm_sequences,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    report_prob_text = build_report_text(
        baseline_prob,
        llm_sequences,
        result_prob,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    print(report_prob_text)

    # 頻度ベースラインで評価
    print(f"\n=== Run {run_idx}: 頻度ベースラインとの比較 ===")
    result_count = compute_metrics(
        baseline_count,
        llm_sequences,
        allow_base_contains_llm=ALLOW_BASELINE_CONTAINS_LLM,
        allow_llm_contains_base=ALLOW_LLM_CONTAINS_BASELINE,
    )
    report_count_text = build_report_text(
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

    # output/llm_direct_{Days} ディレクトリ内の {1,2,3,...}.json を列挙
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
            # ファイル名が数値でない場合はスキップ
            continue

    # 実行結果をDIRECT_LOG_OUTPUT_DIRに保存
    if all_run_reports:
        report_output_path = DIRECT_LOG_OUTPUT_DIR / "evaluate_direct_log_report.txt"
        report_output_path.write_text(
            "\n\n".join(all_run_reports),
            encoding="utf-8",
        )
        print(f"\n評価レポートを保存しました: {report_output_path}")

    # runごとの指標をExcelに保存
    if run_metric_summaries:
        excel_output_path = DIRECT_LOG_OUTPUT_DIR / f"evaluate_direct_log_metrics_{DAYS}days.xlsx"
        save_metrics_excel(run_metric_summaries, excel_output_path)
        print(f"評価指標Excelを保存しました: {excel_output_path}")


if __name__ == "__main__":
    main()
