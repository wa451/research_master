"""
支持度：ウィンドウ内にそのパターンが有るか（時間よりも個数でやったほうが精度良くなる？）
論文と同じように条件ベース評価を行うスクリプト。

入力：
通常のLLM出力JSON（例: llm_sequences_modes_15_1_154days_1.json）

処理概要:
1) CSVから作成した状態系列を、方法A（1時間ごとの固定時間枠）で区切り、
   論文（3.1.2項、3.2.1項）に準拠したトランザクション（バスケット）データを作成する。
2) 各LLMシーケンスの support / confidence / interval_minutes を時間枠ベースで算出する。
3) 閾値ルールで TP/FP を判定
4) Precision / Recall / F1 / Weighted F1 を算出

評価の定義:
- 正例集合（ground truth positives）:
  観測データ上の全連続系列（長さ2〜4）のうち、
  support, confidence, interval_minutes が閾値を満たす系列
- 予測集合（predicted positives）:
  LLMが出力した系列
- TP: 予測集合 ∩ 正例集合
- FP: 予測集合 - 正例集合
- FN: 正例集合 - 予測集合
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Sequence

import pandas as pd
from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR
from src.behavior_pattern_mining.llm.direct_log_extractor import (
    find_state_file,
    load_state_definition,
    map_vectors_to_states,
)
from src.behavior_pattern_mining.visualization.state_transition_visualizer import StateTransitionVisualizer
from src.behavior_pattern_mining.evaluation.metrics import load_sequences


DEFAULT_SUPPORT_MIN = 0.75
DEFAULT_SUPPORT_MAX = 0.85
DEFAULT_SUPPORT_SAMPLES = 20

DEFAULT_CONFIDENCE_MIN = 0.75
DEFAULT_CONFIDENCE_MAX = 0.85
DEFAULT_CONFIDENCE_SAMPLES = 20

# 論文の論文に基づき、1時間枠（60分）で区切るため、枠内での最大時間間隔の上限もデフォルト60分とする
DEFAULT_MAX_INTERVAL_MINUTES = 60.0

JSON_SAFE_INF = 999999.0

PARAM_SUFFIX = f"{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
OUTPUT_DIR = ROOT_DIR / "output" / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
DEFAULT_LLM_SEQUENCES_PATH = OUTPUT_DIR / f"llm_sequences_modes_{PARAM_SUFFIX}_1.json"
DEFAULT_SOURCE_CSV_PATH = ROOT_DIR / "data" / f"{DATASET_NAME}.csv"
DEFAULT_REPORT_PATH = OUTPUT_DIR / f"condition_evaluation_report_{PARAM_SUFFIX}_1.txt"
DEFAULT_SUMMARY_JSON_PATH = OUTPUT_DIR / f"condition_evaluation_summary_{PARAM_SUFFIX}_1.json"
DEFAULT_DETAILS_JSON_PATH = OUTPUT_DIR / f"condition_sequence_metrics_{PARAM_SUFFIX}_1.json"


@dataclass(frozen=True)
class SequenceStats:
    """1系列に対するデータ（時間枠ベース）由来の統計量。"""

    sequence: tuple[str, ...]
    support: float          # 修正①: 「この系列が含まれる時間枠数 / 総時間枠数」
    confidence: float       # 修正②: 「この系列が含まれる時間枠数 / プレフィックスが含まれる時間枠数」
    interval_minutes: float  # この系列が発生した枠内における時間間隔の中央値
    count_sequence: int     # 系列が含まれる枠数
    count_prefix: int       # プレフィックスが含まれる枠数


@dataclass(frozen=True)
class ConditionMetrics:
    """1つの閾値組み合わせに対する評価結果。"""

    support_threshold: float
    confidence_threshold: float
    interval_threshold: float
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    weighted_f1: float
    tp_f1: float
    fp_f1: float
    tp_support: int
    fp_support: int


def build_threshold_grid(min_value: float, max_value: float, samples: int) -> list[float]:
    """指定範囲を等間隔に分割した閾値列を作る。"""
    if samples <= 1:
        return [round(min_value, 4)]

    step = (max_value - min_value) / (samples - 1)
    return [round(min_value + step * index, 4) for index in range(samples)]


def canonicalize_sequence(seq: Sequence[str]) -> tuple[str, ...]:
    """系列を正規化してタプル化する。"""
    return tuple(str(item).strip() for item in seq)


def sequence_to_str(seq: Sequence[str]) -> str:
    """表示用に系列を整形する。"""
    return " -> ".join(seq)


def build_labeled_state_sequence_from_csv(csv_path: Path) -> tuple[list[str], list[pd.Timestamp]]:
    """CSVから状態系列と、対応するタイムスタンプのリスト（pandas.Timestamp型）を取得する。"""
    visualizer = StateTransitionVisualizer(
        n_representative_states=N_STATES,
        hamming_threshold=HAMMING_THRESHOLD,
        data_duration_days=DAYS,
    )

    df = visualizer.load_data(str(csv_path))
    state_vectors_df = visualizer.create_state_vectors(df)

    effective_days = visualizer.effective_data_duration_days
    state_file = find_state_file(DATASET_NAME, N_STATES, HAMMING_THRESHOLD, effective_days)
    _, vector_to_label = load_state_definition(state_file)

    labels, _ = map_vectors_to_states(state_vectors_df, vector_to_label)

    if len(labels) != len(state_vectors_df.index):
        raise ValueError("状態系列とタイムスタンプ長が一致しません")

    timestamps = list(state_vectors_df.index)
    return labels, timestamps


def compute_all_sequence_stats_by_time_window(
    labels: Sequence[str],
    timestamps: list[pd.Timestamp],
    window_hours: float = 1.0,
    min_len: int = 2,
    max_len: int = 4,
) -> dict[tuple[str, ...], SequenceStats]:
    """
    ステップ3（方法A）: データを指定時間（1時間等）ごとの枠に区切り、
    論文に準拠したトランザクションベースで支持度・確信度・時間間隔を集計する。
    """
    if not labels:
        return {}

    # 1. タイムラインデータを1時間ごとの固定枠（セッション）にグルーピングする
    start_time = timestamps[0]
    window_delta = pd.Timedelta(hours=window_hours)
    
    # 枠ごとの (ラベルリスト, タイムスタンプリスト) を格納する
    slots: list[tuple[list[str], list[pd.Timestamp]]] = []
    current_slot_labels: list[str] = []
    current_slot_times: list[pd.Timestamp] = []
    current_window_end = start_time + window_delta

    for label, ts in zip(labels, timestamps):
        while ts >= current_window_end:
            # 次の時間枠へ移行
            slots.append((current_slot_labels, current_slot_times))
            current_slot_labels = []
            current_slot_times = []
            current_window_end += window_delta
        current_slot_labels.append(label)
        current_slot_times.append(ts)
    if current_slot_labels:
        slots.append((current_slot_labels, current_slot_times))

    total_slots = len(slots)
    if total_slots == 0:
        return {}

    # 2. 各時間枠内に「どの系列（およびプレフィックス）が存在するか」を走査して集計
    # 論文の定義に合わせ、1つの枠内で同じ系列が何回起きても「その枠に含まれるか（0か1か）」で数える（バスケット分析）
    seq_slot_count: dict[tuple[str, ...], int] = defaultdict(int)
    prefix_slot_count: dict[tuple[str, ...], int] = defaultdict(int)
    seq_intervals_history: dict[tuple[str, ...], list[float]] = defaultdict(list)

    all_found_sequences: set[tuple[str, ...]] = set()

    for slot_labels, slot_times in slots:
        m = len(slot_labels)
        if m < 2:
            continue

        # この時間枠内で見つかった系列を一時記録するセット（重複カウント防止）
        seen_seq_in_this_slot: set[tuple[str, ...]] = set()
        seen_prefix_in_this_slot: set[tuple[str, ...]] = set()

        # 枠内での隣接時間差を計算
        slot_intervals = [(slot_times[i+1] - slot_times[i]).total_seconds() / 60.0 for i in range(m - 1)]

        # 長さ2〜4の系列をスライド走査
        for length in range(min_len, max_len + 1):
            for start in range(m - length + 1):
                seq = tuple(slot_labels[start : start + length])
                prefix = seq[:-1]

                # プレフィックスの集計（確信度の分母用）
                if prefix not in seen_prefix_in_this_slot:
                    prefix_slot_count[prefix] += 1
                    seen_prefix_in_this_slot.add(prefix)

                # 本系列の集計（支持度の分子用）
                if seq not in seen_seq_in_this_slot:
                    seq_slot_count[seq] += 1
                    seen_seq_in_this_slot.add(seq)
                    all_found_sequences.add(seq)

                # この発生ウィンドウ内での最大時間間隔を取得
                window_intervals = slot_intervals[start : start + length - 1]
                local_max = max(window_intervals) if window_intervals else 0.0
                seq_intervals_history[seq].append(local_max)

    # 3. 論文と同じ定義（枠ベースの割合）で支持度・確信度を算出
    stats_map: dict[tuple[str, ...], SequenceStats] = {}
    for seq in all_found_sequences:
        count_sequence = seq_slot_count[seq]
        count_prefix = prefix_slot_count.get(seq[:-1], 0)

        # 支持度 ＝ 系列が含まれる枠数 / 全時間枠数（これで75%などを超えうる）
        support = safe_divide(count_sequence, total_slots)
        
        # 確信度 ＝ 系列が含まれる枠数 / プレフィックスが含まれる枠数
        confidence = safe_divide(count_sequence, count_prefix)

        # 時間間隔の中央値
        history = seq_intervals_history.get(seq, [])
        interval_minutes = statistics.median(history) if history else JSON_SAFE_INF

        stats_map[seq] = SequenceStats(
            sequence=seq,
            support=support,
            confidence=confidence,
            interval_minutes=interval_minutes,
            count_sequence=count_sequence,
            count_prefix=count_prefix,
        )

    return stats_map


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def passes_threshold(stats: SequenceStats, support_threshold: float, confidence_threshold: float, interval_threshold: float) -> bool:
    return (
        stats.support >= support_threshold
        and stats.confidence >= confidence_threshold
        and stats.interval_minutes <= interval_threshold
    )


def compute_confusion_counts(
    predicted_sequences: set[tuple[str, ...]],
    positive_sequences: set[tuple[str, ...]],
    all_candidates: set[tuple[str, ...]],
) -> tuple[int, int, int, int]:
    tp = len(predicted_sequences & positive_sequences)
    fp = len(predicted_sequences - positive_sequences)
    fn = len(positive_sequences - predicted_sequences)

    negative_sequences = all_candidates - positive_sequences
    tn = len(negative_sequences - predicted_sequences)
    return tp, fp, fn, tn


def compute_metrics_for_thresholds(
    llm_sequences: set[tuple[str, ...]],
    all_candidate_stats: dict[tuple[str, ...], SequenceStats],
    support_threshold: float,
    confidence_threshold: float,
    interval_threshold: float,
) -> ConditionMetrics:
    positive_sequences = {
        seq
        for seq, stats in all_candidate_stats.items()
        if passes_threshold(stats, support_threshold, confidence_threshold, interval_threshold)
    }

    all_candidates = set(all_candidate_stats.keys()) | llm_sequences
    
    tp, fp, fn, tn = compute_confusion_counts(
        predicted_sequences=llm_sequences,
        positive_sequences=positive_sequences,
        all_candidates=all_candidates,
    )

    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(2 * precision * recall, precision + recall)

    tp_f1 = safe_divide(2 * tp, 2 * tp + fp + fn)
    fp_f1 = safe_divide(2 * tn, 2 * tn + fp + fn)

    tp_support = tp + fn
    fp_support = fp + tn
    total = tp_support + fp_support
    weighted_f1 = (
        safe_divide(tp_support, total) * tp_f1
        + safe_divide(fp_support, total) * fp_f1
    )

    return ConditionMetrics(
        support_threshold=support_threshold,
        confidence_threshold=confidence_threshold,
        interval_threshold=interval_threshold,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        weighted_f1=weighted_f1,
        tp_f1=tp_f1,
        fp_f1=fp_f1,
        tp_support=tp_support,
        fp_support=fp_support,
    )


def evaluate_grid(
    llm_sequences: set[tuple[str, ...]],
    all_candidate_stats: dict[tuple[str, ...], SequenceStats],
    support_thresholds: Sequence[float],
    confidence_thresholds: Sequence[float],
    interval_threshold: float,
) -> list[ConditionMetrics]:
    metrics: list[ConditionMetrics] = []
    for support_threshold, confidence_threshold in product(support_thresholds, confidence_thresholds):
        metrics.append(
            compute_metrics_for_thresholds(
                llm_sequences=llm_sequences,
                all_candidate_stats=all_candidate_stats,
                support_threshold=support_threshold,
                confidence_threshold=confidence_threshold,
                interval_threshold=interval_threshold,
            )
        )
    return metrics


def build_report_text(
    llm_sequences: set[tuple[str, ...]],
    support_thresholds: Sequence[float],
    confidence_thresholds: Sequence[float],
    interval_threshold: float,
    threshold_metrics: Sequence[ConditionMetrics],
) -> str:
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("条件ベース評価レポート（論文準拠：1時間固定枠トランザクションベース）")
    lines.append("=" * 80)
    lines.append(f"LLM系列数                        : {len(llm_sequences)}")
    lines.append(
        f"support 閾値グリッド              : {support_thresholds[0]:.4f} 〜 {support_thresholds[-1]:.4f} ({len(support_thresholds)}点)"
    )
    lines.append(
        f"confidence 閾値グリッド           : {confidence_thresholds[0]:.4f} 〜 {confidence_thresholds[-1]:.4f} ({len(confidence_thresholds)}点)"
    )
    lines.append(f"時間枠内 時間間隔上限              : {interval_threshold:.1f} 分")
    lines.append("-")
    lines.append("TP判定式（マーケットバスケット分析の再現）")
    lines.append("  support(枠数割合) >= support_threshold and confidence(枠内発生率) >= confidence_threshold")
    lines.append("-")

    avg_precision = sum(metric.precision for metric in threshold_metrics) / len(threshold_metrics)
    avg_recall = sum(metric.recall for metric in threshold_metrics) / len(threshold_metrics)
    avg_f1 = sum(metric.f1 for metric in threshold_metrics) / len(threshold_metrics)
    avg_weighted_f1 = sum(metric.weighted_f1 for metric in threshold_metrics) / len(threshold_metrics)
    best_metric = max(threshold_metrics, key=lambda metric: metric.weighted_f1)

    lines.append("平均値（全閾値組み合わせの単純平均）")
    lines.append(f"  Precision                        : {avg_precision:.4f}")
    lines.append(f"  Recall                           : {avg_recall:.4f}")
    lines.append(f"  F1-score                         : {avg_f1:.4f}")
    lines.append(f"  Weighted F1-score                : {avg_weighted_f1:.4f}")
    lines.append("-")
    lines.append("最良組み合わせ（Weighted F1 最大）")
    lines.append(f"  support_threshold                : {best_metric.support_threshold:.4f}")
    lines.append(f"  confidence_threshold             : {best_metric.confidence_threshold:.4f}")
    lines.append(f"  interval_threshold               : {best_metric.interval_threshold:.1f}")
    lines.append(f"  TP / FP / FN / TN                : {best_metric.tp} / {best_metric.fp} / {best_metric.fn} / {best_metric.tn}")
    lines.append(f"  Precision                        : {best_metric.precision:.4f}")
    lines.append(f"  Recall                           : {best_metric.recall:.4f}")
    lines.append(f"  F1-score                         : {best_metric.f1:.4f}")
    lines.append(f"  TP class F1                      : {best_metric.tp_f1:.4f}")
    lines.append(f"  FP class F1                      : {best_metric.fp_f1:.4f}")
    lines.append(f"  Weighted F1-score                : {best_metric.weighted_f1:.4f}")
    lines.append("=" * 80)

    return "\n".join(lines)


def save_text_report(report_text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text + "\n", encoding="utf-8")


def save_summary_json(
    support_thresholds: Sequence[float],
    confidence_thresholds: Sequence[float],
    interval_threshold: float,
    threshold_metrics: Sequence[ConditionMetrics],
    output_path: Path,
) -> None:
    average_precision = sum(metric.precision for metric in threshold_metrics) / len(threshold_metrics)
    average_recall = sum(metric.recall for metric in threshold_metrics) / len(threshold_metrics)
    average_f1 = sum(metric.f1 for metric in threshold_metrics) / len(threshold_metrics)
    average_weighted_f1 = sum(metric.weighted_f1 for metric in threshold_metrics) / len(threshold_metrics)
    best_metric = max(threshold_metrics, key=lambda metric: metric.weighted_f1)

    payload = {
        "support_thresholds": list(support_thresholds),
        "confidence_thresholds": list(confidence_thresholds),
        "interval_threshold": interval_threshold,
        "average_metrics": {
            "precision": average_precision,
            "recall": average_recall,
            "f1": average_f1,
            "weighted_f1": average_weighted_f1,
        },
        "best_thresholds": {
            "support_threshold": best_metric.support_threshold,
            "confidence_threshold": best_metric.confidence_threshold,
            "interval_threshold": best_metric.interval_threshold,
            "tp": best_metric.tp,
            "fp": best_metric.fp,
            "fn": best_metric.fn,
            "tn": best_metric.tn,
            "precision": best_metric.precision,
            "recall": best_metric.recall,
            "f1": best_metric.f1,
            "tp_f1": best_metric.tp_f1,
            "fp_f1": best_metric.fp_f1,
            "weighted_f1": best_metric.weighted_f1,
        },
        "all_threshold_metrics": [
            {
                "support_threshold": metric.support_threshold,
                "confidence_threshold": metric.confidence_threshold,
                "interval_threshold": metric.interval_threshold,
                "tp": metric.tp,
                "fp": metric.fp,
                "fn": metric.fn,
                "tn": metric.tn,
                "precision": metric.precision,
                "recall": metric.recall,
                "f1": metric.f1,
                "tp_f1": metric.tp_f1,
                "fp_f1": metric.fp_f1,
                "weighted_f1": metric.weighted_f1,
            }
            for metric in threshold_metrics
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_sequence_details_json(
    llm_sequence_stats: dict[tuple[str, ...], SequenceStats],
    output_path: Path,
) -> None:
    payload = [
        {
            "sequence": list(stats.sequence),
            "sequence_text": sequence_to_str(stats.sequence),
            "support": stats.support,
            "confidence": stats.confidence,
            "interval_minutes": stats.interval_minutes,
            "count_sequence_slots": stats.count_sequence,
            "count_prefix_slots": stats.count_prefix,
        }
        for _, stats in sorted(llm_sequence_stats.items(), key=lambda item: item[0])
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLMシーケンスJSONとCSVから論文準拠の条件ベース評価を行う")
    parser.add_argument("--llm-json", type=Path, default=DEFAULT_LLM_SEQUENCES_PATH, help="LLM系列JSON")
    parser.add_argument("--csv", type=Path, default=DEFAULT_SOURCE_CSV_PATH, help="状態化に使う元CSV")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="出力レポートTXT")
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_JSON_PATH, help="出力サマリーJSON")
    parser.add_argument("--details-json", type=Path, default=DEFAULT_DETAILS_JSON_PATH, help="系列ごとの統計量JSON")
    parser.add_argument("--support-min", type=float, default=DEFAULT_SUPPORT_MIN, help="support 閾値の最小値")
    parser.add_argument("--support-max", type=float, default=DEFAULT_SUPPORT_MAX, help="support 閾値の最大値")
    parser.add_argument("--support-samples", type=int, default=DEFAULT_SUPPORT_SAMPLES, help="support 閾値のサンプル数")
    parser.add_argument("--confidence-min", type=float, default=DEFAULT_CONFIDENCE_MIN, help="confidence 閾値の最小値")
    parser.add_argument("--confidence-max", type=float, default=DEFAULT_CONFIDENCE_MAX, help="confidence 閾値の最大値")
    parser.add_argument("--confidence-samples", type=int, default=DEFAULT_CONFIDENCE_SAMPLES, help="confidence 閾値のサンプル数")
    parser.add_argument("--window-hours", type=float, default=1.0, help="区切る時間枠の長さ（時間単位、デフォルト1.0時間）")
    parser.add_argument("--interval-max", type=float, default=DEFAULT_MAX_INTERVAL_MINUTES, help="時間間隔の上限（分）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    llm_results = load_sequences(args.llm_json)
    llm_sequences = {canonicalize_sequence(seq) for seq in llm_results if len(seq) >= 2}

    labels, timestamps = build_labeled_state_sequence_from_csv(args.csv)
    
    # 時間枠ベースでの一括集計を実行
    all_candidate_stats = compute_all_sequence_stats_by_time_window(
        labels=labels, 
        timestamps=timestamps, 
        window_hours=args.window_hours,
        min_len=2, 
        max_len=4
    )
    
    llm_sequence_stats = {
        seq: all_candidate_stats.get(seq, SequenceStats(seq, 0.0, 0.0, JSON_SAFE_INF, 0, 0))
        for seq in llm_sequences
    }

    support_thresholds = build_threshold_grid(args.support_min, args.support_max, args.support_samples)
    confidence_thresholds = build_threshold_grid(args.confidence_min, args.confidence_max, args.confidence_samples)

    threshold_metrics = evaluate_grid(
        llm_sequences=llm_sequences,
        all_candidate_stats=all_candidate_stats,
        support_thresholds=support_thresholds,
        confidence_thresholds=confidence_thresholds,
        interval_threshold=args.interval_max,
    )

    report_text = build_report_text(
        llm_sequences=llm_sequences,
        support_thresholds=support_thresholds,
        confidence_thresholds=confidence_thresholds,
        interval_threshold=args.interval_max,
        threshold_metrics=threshold_metrics,
    )

    save_text_report(report_text, args.report)
    save_summary_json(
        support_thresholds=support_thresholds,
        confidence_thresholds=confidence_thresholds,
        interval_threshold=args.interval_max,
        threshold_metrics=threshold_metrics,
        output_path=args.summary_json,
    )
    save_sequence_details_json(llm_sequence_stats, args.details_json)

    print(report_text)
    print(f"\n[完了] レポート保存先: {args.report}")


if __name__ == "__main__":
    main()
