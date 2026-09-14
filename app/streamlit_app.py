"""Local Streamlit dashboard for Evaluation 4 through Evaluation 10."""

from __future__ import annotations

from pathlib import Path
import json
import sys

import pandas as pd
import streamlit as st

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.command_builder import (  # noqa: E402
    PROJECT_ROOT,
    EvaluationStep,
    build_evaluation4_steps,
    build_evaluation5_steps,
    build_evaluation6_steps,
    build_evaluation7_steps,
    build_evaluation8_steps,
    build_evaluation9_steps,
    build_evaluation10_steps,
    command_preview,
    default_direct_path,
    default_proposed_path,
    default_state_table,
    display_path,
    proposed_run_path,
    short_suffix,
)
from app.hestia_house_diagrams import (  # noqa: E402
    HOUSE_DESCRIPTIONS,
    HOUSE_TITLES,
    house_topology_dot,
)
from app.hestia_studio_component import render_hestia_studio_component  # noqa: E402
from app.utils import (  # noqa: E402
    append_history,
    discover_result_dirs,
    discover_result_files,
    ensure_log_dir,
    file_status_rows,
    load_history,
    metric_columns,
    run_command,
)
from experiment_config import SMOOTHING_WINDOW_SEC  # noqa: E402


LOG_ROOT = PROJECT_ROOT / "output" / "logs" / "evaluation_dashboard"
DEFAULT_N_STATES = 15
DEFAULT_HAMMING_THRESHOLD = 0

RESULT_GUIDES: dict[str, list[dict[str, str]]] = {
    "評価4": [
        {
            "files": "evaluation_summary.json, adl_metrics_iou_0.3.csv, adl_interval_hit_metrics.csv",
            "how_to_read": "summaryとして、macro/micro平均、ADL別F1、hit rate、後処理で予測数がどれだけ減ったかを見る。",
        },
        {
            "files": "pattern_occurrences.csv, pattern_adl_mapping.csv, filtered_predictions.csv, adl_interval_hit_details.csv",
            "how_to_read": "detailsとして、どのパターンがいつ出現し、どのADLに割り当てられ、どの正解区間をmissしたかを見る。",
        },
        {
            "files": "evaluation_summary.json, configs/adl_min_duration.json, configs/aruba_sensor_map.json",
            "how_to_read": "再現条件として、入力パス、IoU閾値、マージ幅、最小継続時間、センサーマップを確認する。",
        },
    ],
    "評価5": [
        {
            "files": "evaluation5_summary_by_method.csv",
            "how_to_read": "summaryとして、useful_non_redundant_pattern_rate, fragmentation_rate, contextless_useless_rateを手法間で比較する。runsが複数の場合は平均値と標準偏差を見る。",
        },
        {
            "files": "evaluation5_summary_by_method_by_run.csv",
            "how_to_read": "runごとの手法別summaryを確認する。平均値だけでなく、特定runだけ大きく外れていないかを見る。",
        },
        {
            "files": "evaluation5_pattern_details.csv",
            "how_to_read": "detailsとして、run, is_contextless_useless, is_fragmented, fragment_parent_ids, is_useful_non_redundant, evaluation_statusを確認する。",
        },
        {
            "files": "evaluation5_summary.json",
            "how_to_read": "再現条件として、train_period, test_period, thresholds, skipped_methods, FP-Growth設定を確認する。",
        },
    ],
    "評価6": [
        {
            "files": "evaluation6_method_comparison.csv",
            "how_to_read": "summaryとして、手法ごとの平均 Exact Set Match, Jaccard, multilabel Precision / Recall / F1を見る。runsが複数の場合は平均と標準偏差を見る。",
        },
        {
            "files": "evaluation6_method_comparison_by_run.csv",
            "how_to_read": "runごとのばらつきを確認する。平均値だけでなく、特定runだけ大きく外れていないかを見る。",
        },
        {
            "files": "evaluation6_llm_usage_comparison.csv",
            "how_to_read": "手法ごとの1 run合計について、トークン数とAPI応答時間のrun平均・標準偏差を比較する。num_runs_with_complete_metricsも確認する。",
        },
        {
            "files": "evaluation6_pattern_set_details_by_method.csv",
            "how_to_read": "detailsとして、run, method, eval_pattern_id, group_pattern_id, time_band, pred_adl_labels, true_adl_labels, intersection_labels, union_labelsを見てズレの原因を確認する。",
        },
        {
            "files": "evaluation6_by_time_band_by_method.csv, evaluation6_by_pred_label_by_method.csv, evaluation6_by_true_label_by_method.csv",
            "how_to_read": "時間帯別の傾向、付けすぎている予測ラベル、拾えていない正解ラベルを確認する。",
        },
        {
            "files": "evaluation6_comparison_summary.json",
            "how_to_read": "再現条件として、入力パス、run数、14日版で揃っているか、min_overlap_ratio_for_true_label, 許可ラベルを確認する。",
        },
    ],
    "評価7": [
        {
            "files": "evaluation7_condition_summary.csv",
            "how_to_read": "条件ごとの主比較表を見る。rank=1がselection_metricに基づく最適条件で、既定のmean_multilabel_f1はend-to-end F1の後方互換列。",
        },
        {
            "files": "evaluation7_summary.json",
            "how_to_read": "best_conditionと、入力条件、閾値、skipped条件、出力ファイル一覧を確認する。",
        },
        {
            "files": "evaluation7_condition_summary_by_run.csv",
            "how_to_read": "runごとの条件別summaryを見て、平均値だけでなくrun間のばらつきを確認する。",
        },
        {
            "files": "evaluation7_pattern_set_details.csv",
            "how_to_read": "条件別・run別・パターン別の予測ADL集合と正解ADL集合を見て、スコア差の原因を確認する。",
        },
        {
            "files": "evaluation7_by_time_band.csv, evaluation7_by_pred_label.csv, evaluation7_by_true_label.csv",
            "how_to_read": "時間帯別、予測ラベル別、正解ラベル別に、どの条件で精度が変わるかを確認する。",
        },
    ],
    "評価8": [
        {
            "files": "evaluation8_by_frequency_band_by_method.csv, evaluation8_by_frequency_band.csv, evaluation8_by_frequency_band_by_run.csv",
            "how_to_read": "三分位モードではLow / Middle / High、固定帯モードでは回数範囲ごとに、pattern単位のPrecision / Recall / F1とJaccardを比較する。高頻度でPrecisionが高いかは、同一method内の帯間で確認する。",
        },
        {
            "files": "evaluation8_frequency_distribution.png, evaluation8_frequency_band_metrics.png",
            "how_to_read": "154日・提案手法のみの固定帯モードで出力する図。前者は帯ごとの平均パターン数、後者は帯ごとの平均Precision / Recall / F1を示す。",
        },
        {
            "files": "evaluation8_occurrence_weighted_summary.csv",
            "how_to_read": "出現回数で重み付けした全体Jaccard / Precision / Recall / F1を手法ごとに確認する。",
        },
        {
            "files": "evaluation8_frequency_band_details.csv",
            "how_to_read": "各評価レコードの修正前後の出現数、重複除去数、frequency_band、予測/正解ADLラベルを確認して、帯別結果の原因を追跡する。",
        },
        {
            "files": "evaluation8_summary.json",
            "how_to_read": "analysis_scope、入力、有効期間、own-ID・重複除去方針、頻度帯境界を確認する。occurrence_weight_validation.all_passed=trueで、補正後の出現数と頻度加重の総和が一致することも確認する。",
        },
    ],
}

RESULT_FILE_ORDER: dict[str, list[str]] = {
    "評価4": [
        "evaluation_summary.json",
        "adl_metrics_iou_0.3.csv",
        "adl_interval_hit_metrics.csv",
        "adl_metrics_iou_0.5.csv",
        "boundary_metrics_iou_0.3.csv",
        "boundary_metrics_iou_0.5.csv",
        "pattern_occurrences.csv",
        "pattern_adl_mapping.csv",
        "merged_predictions.csv",
        "filtered_predictions.csv",
        "adl_interval_hit_details.csv",
        "state_series.csv",
    ],
    "評価5": [
        "evaluation5_summary_by_method.csv",
        "evaluation5_summary_by_method_by_run.csv",
        "evaluation5_pattern_details.csv",
        "evaluation5_summary.json",
    ],
    "評価6": [
        "evaluation6_method_comparison.csv",
        "evaluation6_method_comparison_by_run.csv",
        "evaluation6_llm_usage_comparison.csv",
        "evaluation6_pattern_set_details_by_method.csv",
        "evaluation6_by_time_band_by_method.csv",
        "evaluation6_by_pred_label_by_method.csv",
        "evaluation6_by_true_label_by_method.csv",
        "evaluation6_comparison_summary.json",
    ],
    "評価7": [
        "evaluation7_condition_summary.csv",
        "evaluation7_summary.json",
        "evaluation7_condition_summary_by_run.csv",
        "evaluation7_pattern_set_details.csv",
        "evaluation7_by_time_band.csv",
        "evaluation7_by_pred_label.csv",
        "evaluation7_by_true_label.csv",
    ],
    "評価8": [
        "evaluation8_frequency_distribution.png",
        "evaluation8_frequency_band_metrics.png",
        "evaluation8_by_frequency_band_by_method.csv",
        "evaluation8_by_frequency_band.csv",
        "evaluation8_by_frequency_band_by_run.csv",
        "evaluation8_occurrence_weighted_summary.csv",
        "evaluation8_frequency_band_details.csv",
        "evaluation8_summary.json",
    ],
}


RESULT_GUIDES["評価9"] = [
    {
        "files": "evaluation9_summary.csv",
        "how_to_read": "condition・method別にcomplete/missing/invalidとcomplete_seedsを先に確認します。回収率、対象活動coverage、Other時間割合、ADL macro-F1の平均・標本標準偏差を読みます。1seedの標準偏差は空欄です。",
    },
    {
        "files": "evaluation9_summary.json",
        "how_to_read": "runsでseed・反復別のstatus、理由、指標・採点コードhashを確認します。欠落を0点にせず、不完全なseedを主集計から除外します。頻度対照のADL指標はnullです。",
    },
]
RESULT_FILE_ORDER["評価9"] = ["evaluation9_summary.csv", "evaluation9_summary.json"]

RESULT_GUIDES["評価10"] = [
    {
        "files": "evaluation10_summary.csv",
        "how_to_read": "methodごとにstatusを確認し、後半で再出現したパターン割合、日単位再現率、遷移被覆率を読みます。llm=missingは0点ではありません。",
    },
    {
        "files": "evaluation10_pattern_details.csv",
        "how_to_read": "系列・時間帯ごとに学習/テスト出現数、出現日数、1日あたり出現率とその比を確認します。",
    },
    {
        "files": "evaluation10_summary.json",
        "how_to_read": "入力hash、manifest timezone、前半/後半の半開区間、K/h/平滑化と警告を確認します。正解ADLがないためADL精度ではありません。",
    },
]
RESULT_FILE_ORDER["評価10"] = [
    "evaluation10_summary.csv",
    "evaluation10_pattern_details.csv",
    "evaluation10_summary.json",
]


def parse_float_list(text: str) -> list[float]:
    values: list[float] = []
    for item in text.replace(",", " ").split():
        if item.strip():
            values.append(float(item))
    return values


def parse_int_list(text: str) -> list[int]:
    values = []
    for item in text.replace(",", " ").split():
        if item.strip():
            values.append(int(item))
    return values


def parse_word_list(text: str) -> list[str]:
    return [item for item in text.replace(",", " ").split() if item]


def rel_default(path: Path) -> str:
    return display_path(path)


def common_sidebar() -> dict:
    st.sidebar.header("共通設定")
    evaluation = st.sidebar.radio(
        "評価を選択",
        ["評価4", "評価5", "評価6", "評価7", "評価8", "評価9", "評価10"],
        horizontal=True,
    )
    runner = st.sidebar.selectbox("Python実行方法", ["uv run python", "python"], index=0)
    run_name = st.sidebar.text_input("run名（ログ用）", "manual")
    smoothing_window_sec = st.sidebar.number_input(
        "チャタリング除去時間（秒）",
        min_value=0,
        value=SMOOTHING_WINDOW_SEC,
        step=1,
        help="同じセンサの遅延OFF窓幅です。0で無効化します。",
        disabled=evaluation == "評価9",
    )
    dry_run = st.sidebar.checkbox("dry-run（実行せずコマンドだけ記録）", value=False)
    st.sidebar.caption(
        "秒数を変更して既存条件を作り直す場合は「全ステップを再実行」を選んでください。"
        "現在の成果物名には秒数が含まれません。"
    )
    if evaluation == "評価9":
        st.sidebar.caption("評価9のseed・日数・平滑化は実験計画ファイルで指定します。共通の平滑化設定は評価9には適用しません。")
    else:
        st.sidebar.caption("seed / overwrite は既存CLI引数がないためUI化していません。")
    return {
        "evaluation": evaluation,
        "runner": runner,
        "run_name": run_name,
        "smoothing_window_sec": int(smoothing_window_sec),
        "dry_run": dry_run,
        "dataset": "aruba",
    }


def render_eval4_settings(common: dict) -> dict:
    st.subheader("評価4: ラベル付きCASASデータによる単一手法ADL評価")
    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.number_input("使用日数", min_value=1, value=154, step=1)
    with col2:
        n_states = st.number_input("代表状態数 K", min_value=1, value=DEFAULT_N_STATES, step=1)
    with col3:
        hamming = st.number_input("ハミング距離閾値", min_value=0, value=DEFAULT_HAMMING_THRESHOLD, step=1)

    default_state = default_state_table("aruba", int(n_states), int(hamming), int(days))
    default_patterns = default_proposed_path("aruba", int(n_states), int(hamming), int(days))

    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    sensor_map = st.text_input("センサーマップ", "configs/aruba_sensor_map.json")
    state_table = st.text_input("代表状態テーブル", rel_default(default_state))
    patterns = st.text_input("評価対象パターンJSON", rel_default(default_patterns))
    state_series = st.text_input("既存state_series CSV（任意）", "")
    event_log = st.text_input("event-log（任意。未指定ならlabeled-casasから再構築）", "")

    st.markdown("**評価パラメータ**")
    col1, col2, col3 = st.columns(3)
    with col1:
        iou_text = st.text_input("IoU閾値（空白区切り）", "0.3 0.5")
        wake_window = st.number_input("wake-window-minutes", min_value=0.0, value=30.0)
        match_mode = st.selectbox("match-mode", ["exact", "skip-other"], index=0)
    with col2:
        max_skip = st.number_input("max-skip-duration-minutes", min_value=0.0, value=1.0)
        merge_gap = st.number_input("merge-gap-minutes", min_value=0.0, value=5.0)
        hit_tolerance = st.number_input("hit-tolerance-minutes", min_value=0.0, value=10.0)
    with col3:
        split_date = st.text_input("split-date（任意）", "")
        train_ratio_text = st.text_input("train-ratio（任意）", "")
        min_duration = st.text_input("min-duration-config（任意）", "configs/adl_min_duration.json")

    st.markdown("**出力**")
    output_dir = st.text_input("output-dir", "results/4_adl_detect")
    write_state = st.text_input("write-state-series", "results/4_adl_detect/state_series.csv")

    return {
        **common,
        "days": int(days),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "labeled_casas": labeled,
        "sensor_map": sensor_map,
        "state_table": state_table,
        "patterns": patterns,
        "state_series": state_series,
        "event_log": event_log,
        "iou_thresholds": parse_float_list(iou_text),
        "wake_window_minutes": wake_window,
        "match_mode": match_mode,
        "max_skip_duration_minutes": max_skip,
        "merge_gap_minutes": merge_gap,
        "hit_tolerance_minutes": hit_tolerance,
        "split_date": split_date,
        "train_ratio": float(train_ratio_text) if train_ratio_text.strip() else None,
        "min_duration_config": min_duration,
        "output_dir": output_dir,
        "write_state_series": write_state,
    }


def render_eval5_settings(common: dict) -> dict:
    st.subheader("評価5: ADLラベルを用いたパターン単位評価")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        days = st.number_input("使用日数", min_value=1, value=154, step=1)
    with col2:
        n_states = st.number_input("代表状態数 K", min_value=1, value=DEFAULT_N_STATES, step=1)
    with col3:
        hamming = st.number_input("ハミング距離閾値", min_value=0, value=DEFAULT_HAMMING_THRESHOLD, step=1)
    with col4:
        runs = st.number_input("runs", min_value=1, value=5, step=1)

    suffix = short_suffix(int(n_states), int(hamming), int(days))
    default_eval5_intermediate = f"output/5_adl_evaluation_{suffix}_fixed"
    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    state_series = st.text_input(
        "state-series",
        f"{default_eval5_intermediate}/state_series_220days.csv",
    )
    state_table = st.text_input("代表状態テーブル", rel_default(default_state_table("aruba", int(n_states), int(hamming), int(days))))
    sensor_map = st.text_input("センサーマップ", "configs/aruba_sensor_map.json")
    patterns_frequency = st.text_input("patterns-frequency", f"output/aruba_{suffix}/state_sequence_counts_{suffix}.json")
    patterns_rule_light = st.text_input("patterns-rule-light", "output/5_rule_filter/frequency_rule_light.csv")
    patterns_rule_medium = st.text_input("patterns-rule-medium", "output/5_rule_filter/frequency_rule_medium.csv")
    patterns_rule_strong = st.text_input("patterns-rule-strong", "output/5_rule_filter/frequency_rule_strong.csv")
    patterns_proposed = st.text_input("patterns-proposed", rel_default(default_proposed_path("aruba", int(n_states), int(hamming), int(days))))
    with st.expander("複数run用テンプレート（任意）"):
        st.caption("使用可能: {dataset}, {n_states}, {hamming_threshold}, {hamming}, {days}, {run}, {suffix}")
        patterns_proposed_template = st.text_input(
            "patterns-proposed-template",
            "",
            placeholder="output/aruba_{suffix}/llm_sequences_modes_{suffix}_{run}.json",
        )
        skip_missing_runs = st.checkbox("skip-missing-runs", value=False)
        proposed_base_path = PROJECT_ROOT / patterns_proposed if not Path(patterns_proposed).is_absolute() else Path(patterns_proposed)
        expected_run_paths = [
            proposed_run_path(
                proposed_base_path,
                patterns_proposed_template,
                "aruba",
                int(n_states),
                int(hamming),
                int(days),
                run,
            )
            for run in range(1, int(runs) + 1)
        ]
        st.dataframe(file_status_rows(expected_run_paths), hide_index=True, use_container_width=True)

    st.markdown("**評価パラメータ**")
    col1, col2, col3 = st.columns(3)
    with col1:
        train_ratio = st.number_input("train-ratio", min_value=0.01, max_value=0.99, value=0.7)
        wake_window = st.number_input("wake-window-minutes", min_value=0.0, value=30.0)
        min_overlap = st.number_input("min-overlap-seconds", min_value=0.0, value=1.0)
        match_mode = st.selectbox("match-mode", ["exact", "skip-other"], index=0)
    with col2:
        grounded_hit = st.number_input("grounded-hit-threshold", min_value=0.0, max_value=1.0, value=0.3)
        grounded_purity = st.number_input("grounded-purity-threshold", min_value=0.0, max_value=1.0, value=0.3)
        useless_hit = st.number_input("useless-hit-threshold", min_value=0.0, max_value=1.0, value=0.1)
        useless_purity = st.number_input("useless-purity-threshold", min_value=0.0, max_value=1.0, value=0.1)
    with col3:
        assigned_purity = st.number_input("assigned-adl-purity-threshold", min_value=0.0, max_value=1.0, value=0.10)
        assigned_max = st.number_input("assigned-adl-max-categories", min_value=1, value=3, step=1)
        max_skip = st.number_input("max-skip-duration-minutes", min_value=0.0, value=2.0)
        other_labels = st.text_input("other-state-labels", "Other Other_ADL unknown その他")

    with st.expander("明示的なtrain/test期間（任意）"):
        train_start = st.text_input("train-start-date", "")
        train_end = st.text_input("train-end-date", "")
        test_start = st.text_input("test-start-date", "")
        test_end = st.text_input("test-end-date", "")

    with st.expander("FP-Growth / baseline生成"):
        enable_fp = st.checkbox("enable-fp-growth-baseline", value=True)
        use_baseline_cache = st.checkbox("use-baseline-cache", value=True)
        baseline_cache_dir = st.text_input(
            "baseline-cache-dir",
            "output/5_adl_correspondence_baselines_fixed",
        )
        st.caption("FP-Growth / transition_probability の生成済みパターンを保存し、同じ条件では再利用します。")
        fp1, fp2, fp3 = st.columns(3)
        with fp1:
            fp_min_support = st.number_input("fp-min-support", min_value=0.0, max_value=1.0, value=0.05)
            fp_top_k = st.number_input("fp-top-k", min_value=1, value=50, step=1)
        with fp2:
            fp_min_len = st.number_input("fp-min-len", min_value=1, value=2, step=1)
            fp_max_len = st.number_input("fp-max-len", min_value=1, value=4, step=1)
        with fp3:
            fp_max_median = st.number_input("fp-max-median-duration-seconds", min_value=0.0, value=1800.0)
            fp_max_p90 = st.number_input("fp-max-p90-duration-seconds", min_value=0.0, value=3600.0)
        exclude_other = st.checkbox("exclude-other-adl-from-any", value=True)
        include_no_test = st.checkbox("include-no-test-support-in-denominator", value=False)
        no_auto = st.checkbox("no-auto-generate-baselines", value=False)

    with st.expander("Transition probability / 新評価指標"):
        enable_transition = st.checkbox("enable-transition-baseline", value=True)
        tr1, tr2, tr3 = st.columns(3)
        with tr1:
            transition_top_k = st.number_input("transition-top-k", min_value=0, value=50, step=1)
            transition_min_prob = st.number_input("transition-min-prob", min_value=0.0, max_value=1.0, value=0.0)
        with tr2:
            transition_min_len = st.number_input("transition-min-len", min_value=2, value=2, step=1)
            transition_max_len = st.number_input("transition-max-len", min_value=2, value=4, step=1)
        with tr3:
            fragmentation_threshold = st.number_input(
                "fragmentation-containment-threshold",
                min_value=0.0,
                max_value=1.0,
                value=0.7,
            )
            low_information_threshold = st.number_input(
                "low-information-threshold",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
            )

    st.markdown("**出力**")
    output_dir = st.text_input("output-dir", "results/5_pattern_quality_fixed")

    return {
        **common,
        "days": int(days),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "runs": int(runs),
        "labeled_casas": labeled,
        "state_series": state_series,
        "state_table": state_table,
        "sensor_map": sensor_map,
        "patterns_frequency": patterns_frequency,
        "patterns_rule_light": patterns_rule_light,
        "patterns_rule_medium": patterns_rule_medium,
        "patterns_rule_strong": patterns_rule_strong,
        "patterns_proposed": patterns_proposed,
        "patterns_proposed_template": patterns_proposed_template,
        "skip_missing_runs": skip_missing_runs,
        "output_dir": output_dir,
        "wake_window_minutes": wake_window,
        "match_mode": match_mode,
        "max_skip_duration_minutes": max_skip,
        "train_ratio": train_ratio,
        "train_start_date": train_start,
        "train_end_date": train_end,
        "test_start_date": test_start,
        "test_end_date": test_end,
        "min_overlap_seconds": min_overlap,
        "grounded_hit_threshold": grounded_hit,
        "grounded_purity_threshold": grounded_purity,
        "useless_hit_threshold": useless_hit,
        "useless_purity_threshold": useless_purity,
        "assigned_adl_purity_threshold": assigned_purity,
        "assigned_adl_max_categories": int(assigned_max),
        "enable_fp_growth_baseline": enable_fp,
        "fp_min_support": fp_min_support,
        "fp_top_k": int(fp_top_k),
        "fp_min_len": int(fp_min_len),
        "fp_max_len": int(fp_max_len),
        "fp_max_median_duration_seconds": fp_max_median,
        "fp_max_p90_duration_seconds": fp_max_p90,
        "use_baseline_cache": use_baseline_cache,
        "baseline_cache_dir": baseline_cache_dir,
        "enable_transition_baseline": enable_transition,
        "transition_top_k": int(transition_top_k),
        "transition_min_prob": transition_min_prob,
        "transition_min_len": int(transition_min_len),
        "transition_max_len": int(transition_max_len),
        "fragmentation_containment_threshold": fragmentation_threshold,
        "low_information_threshold": low_information_threshold,
        "other_state_labels": parse_word_list(other_labels),
        "exclude_other_adl_from_any": exclude_other,
        "include_no_test_support_in_denominator": include_no_test,
        "no_auto_generate_baselines": no_auto,
    }


def render_eval6_settings(common: dict) -> dict:
    st.subheader("評価6: ADL解釈ラベルSet一致評価")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        days = st.number_input("使用日数", min_value=1, value=14, step=1)
    with col2:
        n_states = st.number_input("代表状態数 K", min_value=1, value=DEFAULT_N_STATES, step=1)
    with col3:
        hamming = st.number_input("ハミング距離閾値", min_value=0, value=DEFAULT_HAMMING_THRESHOLD, step=1)
    with col4:
        runs = st.number_input("runs", min_value=1, value=1, step=1)

    suffix = short_suffix(int(n_states), int(hamming), int(days))
    default_intermediate = f"output/6_adl_evaluation_{suffix}"
    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    sensor_map = st.text_input("センサーマップ", "configs/aruba_sensor_map.json")
    state_table = st.text_input("代表状態テーブル", rel_default(default_state_table("aruba", int(n_states), int(hamming), int(days))))
    proposed = st.text_input("patterns-proposed", rel_default(default_proposed_path("aruba", int(n_states), int(hamming), int(days))))
    direct = st.text_input("patterns-direct", rel_default(default_direct_path(int(n_states), int(hamming), int(days))))
    state_series = st.text_input("state-series", f"{default_intermediate}/state_series.csv")
    adl_intervals = st.text_input("adl-intervals（任意。なければlabeled-casasから生成）", "output/adl_label_intervals.csv")

    with st.expander("複数run用テンプレート（任意）"):
        proposed_template = st.text_input("patterns-proposed-template", "")
        direct_template = st.text_input("patterns-direct-template", "")

    st.markdown("**評価パラメータ**")
    col1, col2 = st.columns(2)
    with col1:
        min_ratio = st.number_input("min-overlap-ratio-for-true-label", min_value=0.0, max_value=1.0, value=0.10)
        wake_window = st.number_input("wake-window-minutes", min_value=0.0, value=30.0)
        match_mode = st.selectbox("match-mode", ["exact", "skip-other"], index=0)
    with col2:
        max_skip = st.number_input("max-skip-duration-minutes", min_value=0.0, value=1.0)
        skip_missing = st.checkbox("skip-missing-runs", value=False)
        st.caption(
            "出現なし・正解重なりなし・予測欠落・語彙外は別状態として固定処理します。"
        )
    no_overlap = "Ambiguous"
    missing_pred = "Ambiguous"
    unknown_pred = "Other"

    st.markdown("**出力**")
    intermediate_dir = st.text_input("中間output-dir", default_intermediate)
    output_dir = st.text_input("比較output-dir", "results/6_adl_match")

    return {
        **common,
        "days": int(days),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "runs": int(runs),
        "labeled_casas": labeled,
        "sensor_map": sensor_map,
        "state_table": state_table,
        "patterns_proposed": proposed,
        "patterns_direct": direct,
        "patterns_proposed_template": proposed_template,
        "patterns_direct_template": direct_template,
        "state_series": state_series,
        "adl_intervals": adl_intervals,
        "intermediate_output_dir": intermediate_dir,
        "output_dir": output_dir,
        "min_overlap_ratio_for_true_label": min_ratio,
        "no_overlap_label": no_overlap,
        "missing_pred_label": missing_pred,
        "unknown_pred_label": unknown_pred,
        "wake_window_minutes": wake_window,
        "match_mode": match_mode,
        "max_skip_duration_minutes": max_skip,
        "skip_missing_runs": skip_missing,
    }


def render_eval7_settings(common: dict) -> dict:
    st.subheader("評価7: 提案手法のパラメータ感度分析")
    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.number_input("使用日数", min_value=1, value=30, step=1)
    with col2:
        n_states_text = st.text_input("代表状態数 K（複数指定）", "10,15,20,25,30,35,40")
    with col3:
        hamming_text = st.text_input("ハミング距離閾値（複数指定）", "0,1,2,3")
    try:
        n_states_list = parse_int_list(n_states_text)
        hamming_thresholds = parse_int_list(hamming_text)
    except ValueError:
        st.error("代表状態数Kとハミング距離閾値は整数で指定してください。")
        n_states_list = [DEFAULT_N_STATES]
        hamming_thresholds = [DEFAULT_HAMMING_THRESHOLD]
    if not n_states_list:
        st.warning(f"代表状態数Kが空なので、既定値 {DEFAULT_N_STATES} を使います。")
        n_states_list = [DEFAULT_N_STATES]
    if not hamming_thresholds:
        st.warning(f"ハミング距離閾値が空なので、既定値 {DEFAULT_HAMMING_THRESHOLD} を使います。")
        hamming_thresholds = [DEFAULT_HAMMING_THRESHOLD]

    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    sensor_map = st.text_input("センサーマップ", "configs/aruba_sensor_map.json")
    adl_intervals = st.text_input("adl-intervals（任意。labeled-casasが存在すればそちらを優先）", "output/adl_label_intervals.csv")
    with st.expander("条件別パステンプレート（任意）"):
        st.caption("使用可能: {dataset}, {n_states}, {hamming_threshold}, {hamming}, {days}, {run}, {suffix}")
        patterns_template = st.text_input(
            "patterns-template",
            "",
            placeholder="output/aruba_{suffix}/llm_sequences_modes_{suffix}_{run}.json",
        )
        state_series_template = st.text_input(
            "state-series-template",
            "",
            placeholder="output/6_adl_evaluation_{suffix}/state_series.csv",
        )

    st.markdown("**評価パラメータ**")
    staged_search = st.checkbox(
        "二段階実行（全条件を1回評価 → 上位条件だけ反復）",
        value=True,
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        if staged_search:
            top_n = st.number_input("上位条件数", min_value=1, value=10, step=1)
            total_runs = st.number_input("上位条件の合計実行回数", min_value=2, value=5, step=1)
            runs = 1
            st.caption("初回run 1を平均に含め、不足するrun 2以降だけを追加生成します。")
        else:
            runs = st.number_input("runs", min_value=1, value=1, step=1)
            top_n = 10
            total_runs = 5
        min_ratio = st.number_input("min-overlap-ratio-for-true-label", min_value=0.0, max_value=1.0, value=0.10)
        selection_metric = st.selectbox(
            "selection-metric",
            [
                "mean_multilabel_f1",
                "mean_jaccard",
                "mean_accuracy",
                "mean_exact_set_match",
                "mean_multilabel_precision",
                "mean_multilabel_recall",
            ],
            index=0,
        )
    with col2:
        st.caption(
            "出現なし・正解重なりなし・予測欠落・語彙外は評価6と同じ固定状態で処理します。"
        )
        no_overlap = "Ambiguous"
        missing_pred = "Ambiguous"
        unknown_pred = "Other"
    with col3:
        wake_window = st.number_input("wake-window-minutes", min_value=0.0, value=30.0)
        match_mode = st.selectbox("match-mode", ["exact", "skip-other"], index=0)
        max_skip = st.number_input("max-skip-duration-minutes", min_value=0.0, value=1.0)
    skip_missing_runs = st.checkbox("skip-missing-runs", value=False)
    skip_missing_conditions = st.checkbox("skip-missing-conditions", value=True)
    show_preparation_steps = st.checkbox("不足ファイル作成ステップを表示", value=True)
    if staged_search and patterns_template:
        st.warning("二段階実行の反復生成は標準のoutput命名を使います。patterns-templateは空にしてください。")

    st.markdown("**出力**")
    output_dir = st.text_input("output-dir", "results/7_param_search")

    return {
        **common,
        "days": int(days),
        "n_states_list": n_states_list,
        "hamming_thresholds": hamming_thresholds,
        "runs": int(runs),
        "staged_search": staged_search,
        "top_n": int(top_n),
        "total_runs": int(total_runs),
        "labeled_casas": labeled,
        "sensor_map": sensor_map,
        "adl_intervals": adl_intervals,
        "patterns_template": patterns_template,
        "state_series_template": state_series_template,
        "output_dir": output_dir,
        "min_overlap_ratio_for_true_label": min_ratio,
        "no_overlap_label": no_overlap,
        "missing_pred_label": missing_pred,
        "unknown_pred_label": unknown_pred,
        "wake_window_minutes": wake_window,
        "match_mode": match_mode,
        "max_skip_duration_minutes": max_skip,
        "selection_metric": selection_metric,
        "skip_missing_runs": skip_missing_runs,
        "skip_missing_conditions": skip_missing_conditions,
        "show_preparation_steps": show_preparation_steps,
    }


def evaluation8_scope_config(scope_label: str) -> tuple[str, int]:
    """Map current and persisted Evaluation 8 labels to a CLI scope."""
    if scope_label.startswith("154日"):
        return "proposed_154days", 154
    if scope_label.startswith("30日"):
        return "comparison_30days", 30
    return "comparison_14days", 14


def render_eval8_settings(common: dict) -> dict:
    st.subheader("評価8: 頻度帯別ADL整合性評価")
    st.caption("評価6の指標を置き換えず、出現頻度の三分位または固定回数帯で後段分析します。")
    st.info(
        "チャタリング除去時間は評価8が読む提案手法JSON・state-series・評価6詳細CSVを作成したときの条件です。"
        "評価8の後段集計では再適用しません。"
    )
    scope_label = st.radio(
        "実行条件",
        ["154日: 提案手法のみ", "14日: 提案手法 vs LLM単独ベースライン"],
        index=0,
        horizontal=True,
        key="evaluation8_analysis_scope",
    )
    # A previous dashboard version exposed a 30-day comparison label.  Treat a
    # persisted value from that version as comparison rather than accidentally
    # sending it through the 154-day proposed-only branch.
    analysis_scope, days = evaluation8_scope_config(scope_label)

    col1, col2, col3 = st.columns(3)
    with col1:
        n_states = st.number_input("代表状態数 K", min_value=1, value=DEFAULT_N_STATES, step=1)
    with col2:
        hamming = st.number_input("ハミング距離閾値", min_value=0, value=DEFAULT_HAMMING_THRESHOLD, step=1)
    with col3:
        runs = st.number_input("runs", min_value=1, value=5, step=1)
    suffix = short_suffix(int(n_states), int(hamming), days)

    st.markdown("**入力・出力**")
    if analysis_scope in {"comparison_14days", "comparison_30days"}:
        details = st.text_input(
            "evaluation6 details file path",
            f"results/6_adl_match/{suffix}/evaluation6_pattern_set_details_by_method.csv",
        )
        patterns_proposed = ""
        state_series = st.text_input(
            "state-series（評価8でown-ID出現数を再構築）",
            f"output/6_adl_evaluation_{suffix}/state_series.csv",
        )
        labeled_casas = ""
        adl_intervals = ""
        output_dir = st.text_input(
            "output directory",
            "results/8_vs_llm_own_id_fixed",
        )
        st.caption("評価6詳細CSVには5 run分のレコードを含めてください。評価8ではrunごとの帯別指標を平均します。")
        patterns_proposed_template = ""
        runs = 5
    else:
        details = ""
        patterns_proposed = st.text_input(
            "patterns-proposed (154日)",
            f"output/aruba_{suffix}/llm_sequences_modes_{suffix}_1.json",
        )
        state_series_default = (
            "output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv"
            if (int(n_states), int(hamming)) == (DEFAULT_N_STATES, DEFAULT_HAMMING_THRESHOLD)
            else ""
        )
        state_series = st.text_input("state-series (154日)", state_series_default)
        if not state_series_default:
            st.caption("Kまたはハミング距離を変更した場合は、その条件で作成した154日state-series CSVを指定してください。")
        labeled_casas = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
        adl_intervals = st.text_input("adl-intervals（任意）", "output/adl_label_intervals.csv")
        patterns_proposed_template = st.text_input(
            "patterns-proposed-template（任意）",
            "",
            placeholder="output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_{run}.json",
        )
        output_dir = st.text_input(
            "output directory",
            "results/8_proposed_own_id_fixed",
        )
    frequency_band_mode = "both"
    st.markdown("**頻度帯評価: 三分位 + 固定回数帯（同時実行）**")
    fixed_frequency_bin_edges = st.text_input(
        "固定頻度境界（カンマまたは空白区切り）",
        "0,1,10,100,1000,10000",
        help="各帯の下限です。0,1,10,100,1000,10000 は 0回、1–9回、…、10,000回以上を表します。",
    )
    write_distribution_plots = True
    st.caption(
        "同じ評価レコードから三分位と固定回数帯を続けて集計し、結果を output directory の "
        "tertile/ と fixed/ に分けて保存します。"
    )
    if analysis_scope == "proposed_154days":
        write_distribution_plots = st.checkbox("固定回数帯の分布図・帯別指標図を保存", value=True)

    return {
        **common,
        "analysis_scope": analysis_scope,
        "days": days,
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "evaluation6_details": details,
        "patterns_proposed": patterns_proposed,
        "patterns_proposed_template": patterns_proposed_template,
        "state_series": state_series,
        "labeled_casas": labeled_casas,
        "adl_intervals": adl_intervals,
        "output_dir": output_dir,
        "frequency_band_mode": frequency_band_mode,
        "fixed_frequency_bin_edges": fixed_frequency_bin_edges,
        "write_distribution_plots": write_distribution_plots,
        "runs": int(runs),
        "min_overlap_ratio_for_true_label": 0.10,
        "no_overlap_label": "Ambiguous",
        "missing_pred_label": "Ambiguous",
        "unknown_pred_label": "Other",
        "wake_window_minutes": 30.0,
        "match_mode": "exact",
        "max_skip_duration_minutes": 1.0,
    }


def render_hestia_house_connections() -> None:
    """Show the three evaluation-9 house graphs without changing execution settings."""
    with st.expander("3住宅のつながり", expanded=True):
        st.caption(
            "青色は接続の中心となる空間、破線は屋外です。線にはドアセンサーIDと移動時間を表示します。"
            "base / large variability は同じ住宅構造を使います。"
        )
        columns = st.columns(3)
        for column, house in zip(
            columns, ("compact", "corridor", "branched"), strict=True
        ):
            with column:
                st.markdown(f"#### {HOUSE_TITLES[house]}")
                st.caption(HOUSE_DESCRIPTIONS[house])
                st.graphviz_chart(house_topology_dot(house), width="stretch")


def render_eval9_settings(common: dict) -> dict:
    st.subheader("評価9: Hestia合成ログによる系列回収・ADL意味対応")
    st.caption("手順・指標: docs/evaluations/evaluation_9_hestia.md。実Arubaの評価とは別に集計します。")
    st.info("既定は4条件×1seed×4日のpilotです。平滑化・K・seed・日数は計画ファイルの値を使います。")
    render_hestia_house_connections()
    hestia_root = st.text_input("Hestiaディレクトリ", "Hestia")
    plan = st.text_input(
        "実験計画（JSON / YAML）", "Hestia/examples/experiments/noise_free_pilot.yaml"
    )
    experiment = st.text_input("生成ログ・中間成果物ディレクトリ", "output/9_hestia/pilot")
    output_dir = st.text_input("評価9の集計先", "results/9_hestia/pilot")
    method = st.selectbox("採点する手法", ["both", "frequency", "llm"])
    allow_api = st.checkbox("LLM抽出のAPI呼出しを許可（費用が発生します）", value=False)
    st.caption(
        "既存のexperiment.jsonとruns/を持つ実験も指定できます。単体のStudio CSVはこの評価の入力契約とは異なります。"
    )
    st.caption(
        "評価9は一括実行時も各段階のハッシュを検証します。完了済み生成・前処理・LLMは既存CLIが検証して再利用します。設定変更時は新しい出力先を指定してください。"
    )
    if allow_api:
        st.warning(
            "ステップ4または一括実行で有料APIを呼びます。先に許可OFFのステップ4でモデルと呼出し数を確認できます。"
        )
    return {
        **common,
        "hestia_root": hestia_root,
        "plan": plan,
        "experiment": experiment,
        "output_dir": output_dir,
        "method": method,
        "allow_api": allow_api,
    }


def render_eval10_settings(common: dict) -> dict:
    st.subheader("評価10: SwitchBot実宅ログの時間ホールドアウト評価")
    st.caption("前半だけで生成し、固定した状態表で後半の再出現を評価します。正解ADL精度ではありません。")
    snapshot = st.text_input(
        "SwitchBotスナップショット",
        "data/switchbot/2026-09-01_2026-09-08",
    )
    snapshot_name = Path(snapshot.rstrip("/")).name or "snapshot"
    output_dir = st.text_input(
        "中間成果物ディレクトリ", f"output/10_switchbot/{snapshot_name}"
    )
    results_dir = st.text_input(
        "評価10の集計先", f"results/10_switchbot/{snapshot_name}"
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        train_ratio = st.number_input(
            "学習期間比率", min_value=0.1, max_value=0.9, value=0.7, step=0.1
        )
    with col2:
        n_states = st.number_input(
            "代表状態数 K", min_value=1, value=DEFAULT_N_STATES, step=1
        )
    with col3:
        hamming = st.number_input(
            "ハミング距離閾値", min_value=0, value=DEFAULT_HAMMING_THRESHOLD, step=1
        )
    split_at = st.text_input("テスト開始（任意・現地時刻の0時）", "")
    sampling_seconds = st.number_input("サンプリング間隔（秒）", min_value=1, value=1, step=1)
    min_sequence_length = st.number_input("最小系列長", min_value=2, value=2, step=1)
    max_sequence_length = st.number_input(
        "最大系列長", min_value=int(min_sequence_length), value=max(4, int(min_sequence_length)), step=1
    )
    min_train_occurrences = st.number_input("学習側の最小出現回数", min_value=1, value=2, step=1)
    top_k_per_mode = st.number_input("時間帯ごとの最大頻出系列数", min_value=1, value=20, step=1)
    method = st.selectbox("採点する手法", ["both", "frequency", "llm"])
    allow_api = st.checkbox("LLM抽出のAPI呼出しを許可（費用が発生します）", value=False)
    if allow_api:
        st.warning("一括実行またはステップ2でGemini APIを呼びます。")
    return {
        **common,
        "snapshot": snapshot,
        "output_dir": output_dir,
        "results_dir": results_dir,
        "split_at": split_at,
        "train_ratio": float(train_ratio),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "sampling_seconds": int(sampling_seconds),
        "min_sequence_length": int(min_sequence_length),
        "max_sequence_length": int(max_sequence_length),
        "min_train_occurrences": int(min_train_occurrences),
        "top_k_per_mode": int(top_k_per_mode),
        "method": method,
        "allow_api": allow_api,
    }


def render_hestia_studio(_common: dict) -> None:
    """Mount Hestia's visual scenario editor as a Components v2 component."""
    st.subheader("Hestia Studio")
    st.caption(
        "Hestia StudioはこのStreamlitプロセス内で動作します。別サーバーやポートは使用しません。"
    )
    st.info(
        "Studio内の住宅タブを切り替えても、各住宅の未保存編集はページを開いている間保持されます。"
        "ページを再読み込みする前に、必要な編集を「YAML保存」でHestia/scenarios/へ保存してください。"
        "保存したカスタムシナリオは評価9の本実験planへ自動反映されません。"
    )
    render_hestia_studio_component()


def render_step(step: EvaluationStep, settings: dict) -> None:
    expanded = not (step.step_id.startswith("eval7_") and step.step_id != "eval7_evaluate")
    with st.expander(step.title, expanded=expanded):
        st.caption(step.description)
        st.code(command_preview(step.command), language="bash")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("入力ファイル")
            st.dataframe(file_status_rows(step.required_inputs), hide_index=True, use_container_width=True)
        with col2:
            st.markdown("出力ファイル")
            st.dataframe(file_status_rows(step.expected_outputs), hide_index=True, use_container_width=True)

        missing_inputs = [path for path in step.required_inputs if not path.exists()]
        if missing_inputs:
            st.warning("不足している入力があります。前段ステップを実行するか、パスを確認してください。")

        button_label = "dry-run記録" if settings["dry_run"] else "このステップを実行"
        if st.button(button_label, key=f"run_{step.step_id}"):
            log_dir = ensure_log_dir(LOG_ROOT, settings["evaluation"], settings["run_name"])
            log_path = log_dir / f"{step.step_id}.log"
            record = {
                "evaluation": settings["evaluation"],
                "step_id": step.step_id,
                "title": step.title,
                "dry_run": settings["dry_run"],
                "command": step.command,
                "command_preview": command_preview(step.command),
                "log_path": display_path(log_path),
            }
            append_history(LOG_ROOT, record)
            if settings["dry_run"]:
                log_path.write_text(command_preview(step.command) + "\n", encoding="utf-8")
                st.info(f"dry-runとして記録しました: {display_path(log_path)}")
                return

            output_box = st.empty()

            def update_output(text: str) -> None:
                output_box.text_area("実行ログ", text, height=320)

            with st.spinner("実行中..."):
                result = run_command(step.command, cwd=PROJECT_ROOT, log_path=log_path, on_output=update_output)
            if result.returncode == 0:
                st.success(f"成功: {result.elapsed_seconds:.1f}s / log: {display_path(result.log_path)}")
            else:
                st.error(f"失敗: exit={result.returncode} / {result.elapsed_seconds:.1f}s / log: {display_path(result.log_path)}")
                st.text_area("ログ末尾", result.output[-8000:], height=260)


FINAL_EVALUATION_STEP_IDS = {
    "eval4_evaluate",
    "eval5_evaluate",
    "eval6_compare",
    "eval7_evaluate",
    "eval9_evaluate",
    "eval10_evaluate",
}


def missing_expected_outputs(step: EvaluationStep) -> list[Path]:
    return [path for path in step.expected_outputs if not path.exists()]


def is_batch_generation_step(step: EvaluationStep) -> bool:
    return step.step_id not in FINAL_EVALUATION_STEP_IDS


def is_final_evaluation_step(step: EvaluationStep) -> bool:
    return step.step_id in FINAL_EVALUATION_STEP_IDS


def batch_target_steps(steps: list[EvaluationStep], mode: str) -> list[EvaluationStep]:
    if mode == "全ステップを再実行":
        return steps
    if mode == "不足ファイル生成 + 評価本体":
        return [
            step
            for step in steps
            if (is_batch_generation_step(step) and (step.verify_on_batch or missing_expected_outputs(step)))
            or is_final_evaluation_step(step)
        ]
    return [
        step
        for step in steps
        if is_batch_generation_step(step) and (step.verify_on_batch or missing_expected_outputs(step))
    ]


def batch_mode_description(mode: str) -> str:
    if mode == "全ステップを再実行":
        return "表示中の全ステップを上から順に実行します。既存出力があっても各コマンドを再実行します。"
    if mode == "不足ファイル生成 + 評価本体":
        return "前段ステップは期待出力が不足しているものだけ実行し、その後に評価本体/比較本体を実行します。"
    return "評価本体は実行せず、前段ステップのうち期待出力が不足しているコマンドだけを上から順に実行します。"


def render_batch_runner(steps: list[EvaluationStep], settings: dict) -> None:
    st.markdown("### 一括実行")
    mode = st.radio(
        "一括実行モード",
        ["不足ファイル生成のみ", "不足ファイル生成 + 評価本体", "全ステップを再実行"],
        horizontal=True,
    )
    st.caption(batch_mode_description(mode))

    targets = batch_target_steps(steps, mode)
    if not targets:
        st.success("このモードで実行対象になるステップはありません。")
        return

    with st.expander("一括実行対象", expanded=False):
        for step in targets:
            missing_outputs = ", ".join(display_path(path) for path in missing_expected_outputs(step))
            suffix = f" / 不足出力: `{missing_outputs}`" if missing_outputs else ""
            st.markdown(f"- {step.title}{suffix}")

    label = "dry-runで一括実行コマンドを記録" if settings["dry_run"] else "選択モードで一括実行"
    if not st.button(label, key=f"run_all_{settings['evaluation']}_{mode}"):
        return

    log_dir = ensure_log_dir(LOG_ROOT, settings["evaluation"], f"{settings['run_name']}_batch")
    st.info(f"一括実行ログ: {display_path(log_dir)}")

    completed = 0
    for index, step in enumerate(targets, start=1):
        st.markdown(f"**{index}. {step.title}**")
        st.code(command_preview(step.command), language="bash")
        log_path = log_dir / f"{index:02d}_{step.step_id}.log"

        record = {
            "evaluation": settings["evaluation"],
            "step_id": step.step_id,
            "title": step.title,
            "dry_run": settings["dry_run"],
            "batch": True,
            "batch_mode": mode,
            "command": step.command,
            "command_preview": command_preview(step.command),
            "log_path": display_path(log_path),
        }

        missing_inputs = [path for path in step.required_inputs if not path.exists()]
        if missing_inputs and not settings["dry_run"]:
            missing_text = "\n".join(f"- {display_path(path)}" for path in missing_inputs)
            log_path.write_text(
                f"$ {command_preview(step.command)}\n\nSTOPPED: missing required inputs.\n{missing_text}\n",
                encoding="utf-8",
            )
            append_history(LOG_ROOT, {**record, "status": "blocked_missing_inputs"})
            st.error(f"停止: 必要な入力が不足しています / log: {display_path(log_path)}")
            st.text(missing_text)
            break

        append_history(LOG_ROOT, record)
        if settings["dry_run"]:
            log_path.write_text(command_preview(step.command) + "\n", encoding="utf-8")
            completed += 1
            st.info(f"dry-runとして記録しました: {display_path(log_path)}")
            continue

        output_box = st.empty()

        def update_output(text: str, *, step_index: int = index, step_id: str = step.step_id) -> None:
            output_box.text_area(f"実行ログ {step_index}: {step_id}", text, height=260)

        with st.spinner(f"実行中: {step.title}"):
            result = run_command(step.command, cwd=PROJECT_ROOT, log_path=log_path, on_output=update_output)
        if result.returncode == 0:
            completed += 1
            st.success(f"成功: {result.elapsed_seconds:.1f}s / log: {display_path(result.log_path)}")
            continue

        st.error(f"失敗: exit={result.returncode} / {result.elapsed_seconds:.1f}s / log: {display_path(result.log_path)}")
        st.text_area(f"ログ末尾 {step.step_id}", result.output[-8000:], height=260)
        break
    else:
        st.success(f"一括実行が完了しました。実行/記録: {completed}")


def infer_evaluation_for_results(selected_dir: Path, files: list[Path], current_evaluation: str | None) -> str | None:
    names = {path.name for path in files}
    if any(name.startswith("evaluation10_") for name in names):
        return "評価10"
    if any(name.startswith("evaluation9_") for name in names):
        return "評価9"
    if any(name.startswith("evaluation8_") for name in names):
        return "評価8"
    if any(name.startswith("evaluation7_") for name in names):
        return "評価7"
    if any(name.startswith("evaluation6_") for name in names):
        return "評価6"
    if any(name.startswith("evaluation5_") for name in names):
        return "評価5"
    if {"evaluation_summary.json", "adl_interval_hit_metrics.csv"} & names or "4_adl_detect" in str(selected_dir):
        return "評価4"
    if current_evaluation in RESULT_GUIDES:
        return current_evaluation
    return None


def result_file_rank(evaluation: str | None, path: Path) -> tuple[int, str]:
    if not evaluation:
        return (999, path.name)
    order = RESULT_FILE_ORDER.get(evaluation, [])
    try:
        return (order.index(path.name), path.name)
    except ValueError:
        return (999, path.name)


def result_file_description(evaluation: str | None, selected_file: Path) -> str:
    if not evaluation:
        return ""
    for guide in RESULT_GUIDES.get(evaluation, []):
        file_names = [name.strip(" `") for name in guide["files"].split(",")]
        if selected_file.name in file_names:
            return guide["how_to_read"]
    return ""


def render_result_guide(evaluation: str | None) -> None:
    if not evaluation:
        return
    guide = RESULT_GUIDES.get(evaluation, [])
    if not guide:
        return
    st.markdown("**結果の読み方**")
    guide_rows = [
        {"順序": index, "見るファイル": item["files"], "どう見るか": item["how_to_read"]}
        for index, item in enumerate(guide, start=1)
    ]
    st.dataframe(pd.DataFrame(guide_rows), hide_index=True, use_container_width=True)


def render_csv_result_table(df: pd.DataFrame, *, key_prefix: str) -> pd.DataFrame:
    columns = list(df.columns)
    default_columns = st.session_state.get(f"{key_prefix}_columns", columns)
    default_columns = [column for column in default_columns if column in columns] or columns
    selected_columns = st.multiselect(
        "表示するカラム",
        columns,
        default=default_columns,
        key=f"{key_prefix}_columns",
    )
    if not selected_columns:
        st.warning("少なくとも1つのカラムを選択してください。")
        return df.iloc[:, 0:0]
    filtered_df = df[selected_columns]
    st.dataframe(filtered_df, use_container_width=True)
    return filtered_df


def render_results(default_dirs: list[Path], current_evaluation: str | None = None) -> None:
    st.subheader("結果表示")
    all_dirs = discover_result_dirs()
    for directory in default_dirs:
        if directory.exists() and directory not in all_dirs:
            all_dirs.append(directory)
    all_dirs = sorted(set(all_dirs))
    if not all_dirs:
        st.info("表示できる結果ディレクトリがまだありません。")
        return

    labels = [display_path(path) for path in all_dirs]
    selected_label = st.selectbox("結果ディレクトリ", labels)
    selected_dir = all_dirs[labels.index(selected_label)]
    files = discover_result_files([selected_dir])
    if not files:
        st.info("CSV/JSON/PNGが見つかりません。")
        return
    evaluation = infer_evaluation_for_results(selected_dir, files, current_evaluation)
    render_result_guide(evaluation)

    files = sorted(files, key=lambda path: result_file_rank(evaluation, path))
    file_labels = [display_path(path) for path in files]
    selected_file_label = st.selectbox("表示ファイル", file_labels)
    selected_file = files[file_labels.index(selected_file_label)]
    description = result_file_description(evaluation, selected_file)

    if selected_file.suffix == ".csv":
        df = pd.read_csv(selected_file)
        filtered_df = render_csv_result_table(df, key_prefix=f"result_{selected_file}")
        if selected_file.name in {"evaluation8_by_frequency_band.csv", "evaluation8_by_frequency_band_by_method.csv"}:
            simple_columns = [
                column
                for column in [
                    "method",
                    "frequency_band",
                    "mean_multilabel_precision",
                    "mean_multilabel_recall",
                    "mean_multilabel_f1",
                ]
                if column in df.columns
            ]
            if simple_columns:
                st.markdown("**頻度帯別 Precision / Recall / F1**")
                st.dataframe(df[simple_columns], hide_index=True, use_container_width=True)
        metrics = metric_columns(filtered_df.columns)
        if metrics:
            metric = st.selectbox("グラフ化する指標", metrics)
            if "method" in filtered_df.columns:
                chart_df = filtered_df[["method", metric]].dropna().set_index("method")
                st.bar_chart(chart_df)
            elif "adl_category" in filtered_df.columns:
                chart_df = filtered_df[["adl_category", metric]].dropna().set_index("adl_category")
                st.bar_chart(chart_df)
            elif "category" in filtered_df.columns:
                chart_df = filtered_df[["category", metric]].dropna().set_index("category")
                st.bar_chart(chart_df)
            elif "condition_id" in filtered_df.columns:
                chart_df = filtered_df[["condition_id", metric]].dropna().set_index("condition_id")
                st.bar_chart(chart_df)
    elif selected_file.suffix == ".json":
        payload = json.loads(selected_file.read_text(encoding="utf-8"))
        st.json(payload)
    else:
        st.image(str(selected_file), caption=selected_file.name, use_container_width=True)
    if description:
        st.info(f"このファイルの見方: {description}")

    eval7_summary = selected_dir / "evaluation7_summary.json"
    if eval7_summary.exists():
        payload = json.loads(eval7_summary.read_text(encoding="utf-8"))
        best = payload.get("best_condition")
        if best:
            st.markdown("**評価7 最適条件**")
            st.json(
                {
                    "condition_id": best.get("condition_id"),
                    "n_states": best.get("n_states"),
                    "hamming_threshold": best.get("hamming_threshold"),
                    "selection_metric": best.get("selection_metric"),
                    "selection_metric_value": best.get("selection_metric_value"),
                }
            )

    st.markdown("**複数run比較**")
    comparison_files = [path for path in discover_result_files([PROJECT_ROOT / "results"]) if path.name in {"evaluation8_by_frequency_band_by_method.csv", "evaluation8_by_frequency_band_by_run.csv", "evaluation7_condition_summary.csv", "evaluation6_method_comparison.csv", "evaluation6_llm_usage_comparison.csv", "evaluation5_summary_by_method.csv", "evaluation5_summary_by_method_by_run.csv", "adl_interval_hit_metrics.csv"}]
    if comparison_files:
        chosen = st.multiselect("比較に使うCSV", [display_path(path) for path in comparison_files], default=[display_path(comparison_files[0])])
        frames = []
        label_to_path = {display_path(path): path for path in comparison_files}
        for label in chosen:
            df = pd.read_csv(label_to_path[label])
            df.insert(0, "source", label)
            frames.append(df)
        if frames:
            render_csv_result_table(pd.concat(frames, ignore_index=True), key_prefix="run_comparison")


def render_logs() -> None:
    st.subheader("ログ確認")
    records = load_history(LOG_ROOT)
    if not records:
        st.info("まだコマンド履歴がありません。")
        return
    df = pd.DataFrame(records)
    st.dataframe(df, use_container_width=True)
    log_files = sorted(LOG_ROOT.rglob("*.log")) if LOG_ROOT.exists() else []
    if log_files:
        labels = [display_path(path) for path in log_files]
        selected = st.selectbox("ログファイル", labels, index=len(labels) - 1)
        path = log_files[labels.index(selected)]
        st.text_area("ログ内容", path.read_text(encoding="utf-8", errors="replace")[-20000:], height=420)


def default_result_dirs(settings: dict) -> list[Path]:
    evaluation = settings["evaluation"]
    if evaluation == "評価4":
        return [PROJECT_ROOT / settings["output_dir"]]
    if evaluation == "評価5":
        return [PROJECT_ROOT / settings["output_dir"]]
    if evaluation == "評価7":
        return [PROJECT_ROOT / settings["output_dir"]]
    if evaluation in ("評価8", "評価9"):
        return [PROJECT_ROOT / settings["output_dir"]]
    if evaluation == "評価10":
        return [PROJECT_ROOT / settings["results_dir"]]
    suffix = short_suffix(settings["n_states"], settings["hamming_threshold"], settings["days"])
    output_dir = PROJECT_ROOT / settings["output_dir"]
    return [output_dir / suffix if output_dir.name != suffix else output_dir, PROJECT_ROOT / settings["intermediate_output_dir"]]


def main() -> None:
    st.set_page_config(page_title="研究評価ダッシュボード", layout="wide")
    st.title("研究評価ダッシュボード")
    st.caption("評価4〜10とHestia Studioを1つにまとめたローカル研究Webアプリです。")

    common = common_sidebar()
    run_tab, studio_tab, result_tab, log_tab = st.tabs(
        ["ステップ実行", "Hestia Studio", "結果比較", "ログ確認"]
    )

    with run_tab:
        if common["evaluation"] == "評価4":
            settings = render_eval4_settings(common)
            steps = build_evaluation4_steps(settings)
        elif common["evaluation"] == "評価5":
            settings = render_eval5_settings(common)
            steps = build_evaluation5_steps(settings)
        elif common["evaluation"] == "評価6":
            settings = render_eval6_settings(common)
            steps = build_evaluation6_steps(settings)
        elif common["evaluation"] == "評価7":
            settings = render_eval7_settings(common)
            steps = build_evaluation7_steps(settings)
        elif common["evaluation"] == "評価8":
            settings = render_eval8_settings(common)
            steps = build_evaluation8_steps(settings)
        elif common["evaluation"] == "評価9":
            settings = render_eval9_settings(common)
            steps = build_evaluation9_steps(settings)
        else:
            settings = render_eval10_settings(common)
            steps = build_evaluation10_steps(settings)

        st.markdown("### ステップ")
        render_batch_runner(steps, settings)
        for step in steps:
            render_step(step, settings)

    with result_tab:
        try:
            render_results(default_result_dirs(settings), common["evaluation"])
        except NameError:
            render_results([])

    with studio_tab:
        render_hestia_studio(common)

    with log_tab:
        render_logs()


if __name__ == "__main__":
    main()
