"""Local Streamlit dashboard for Evaluation 4 through Evaluation 10."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
    build_evaluation6_strict_ablation_steps,
    build_evaluation7_steps,
    build_evaluation8_steps,
    build_evaluation9_steps,
    build_evaluation10_steps,
    build_llm_response_smoke_test_step,
    command_preview,
    default_direct_path,
    default_proposed_path,
    default_state_table,
    display_path,
    proposed_run_path,
    short_suffix,
)
from app.batch_runner import (  # noqa: E402
    ACTIVE_BATCH_STATUSES,
    create_batch_artifacts,
    discover_batch_statuses,
    launch_batch_worker,
    recent_finished_batches,
    request_batch_cancellation,
)
from app.evaluation9_plan import (  # noqa: E402
    DURATION_PRESET,
    DURATION_TRAIN_DAYS,
    PRESET_PLAN_FILENAMES,
    archive_evaluation9_outputs,
    build_effective_plan,
    current_preparation_provenance_suffix,
    estimate_scale,
    experiment_snapshot_matches,
    load_preset_plan,
    parse_seed_list,
    preparation_provenance_matches,
    preset_directory_name,
    save_effective_plan,
)
from app.hestia_house_diagrams import (  # noqa: E402
    HOUSE_DESCRIPTIONS,
    HOUSE_TITLES,
    house_topology_dot,
)
from app.hestia_studio_component import render_hestia_studio_component  # noqa: E402
from app.model_selection import (  # noqa: E402
    DASHBOARD_MODELS,
    DEFAULT_DASHBOARD_MODEL_ID,
    dashboard_model,
)
from app.utils import (  # noqa: E402
    append_history,
    discover_result_dirs,
    discover_result_files,
    ensure_log_dir,
    file_status_rows,
    load_history,
    metric_columns,
    now_stamp,
    run_command,
)
from experiment_config import (  # noqa: E402
    SMOOTHING_WINDOW_SEC,
    current_model_output_root,
    current_model_results_root,
)
from src.behavior_pattern_mining.evaluation.evaluation7_staged import (  # noqa: E402
    FORMAL_EVALUATION7_DAYS,
    FORMAL_EVALUATION7_HAMMING,
    FORMAL_EVALUATION7_N_STATES,
    FORMAL_EVALUATION7_RESULTS_DIRNAME,
    FORMAL_EVALUATION7_RUNS,
)
from src.behavior_pattern_mining.evaluation.evaluation10_switchbot import (  # noqa: E402
    FORMAL_EVALUATION7_BEST_CONDITION_MANIFEST,
)
from src.behavior_pattern_mining.data.sensor_representation import (  # noqa: E402
    DEFAULT_SENSOR_REPRESENTATION,
    SENSOR_REPRESENTATIONS,
    artifact_dataset_name,
    sensor_map_path,
)


DEFAULT_N_STATES = 10
DEFAULT_HAMMING_THRESHOLD = 2
FABLE5_MODEL_ID = "us.anthropic.claude-fable-5"

# These paths hold the compatible artifacts produced in the current Fable 5
# dashboard session. Keep their plan/provenance suffixes so Hestia can resume.
FABLE5_EVALUATION9_ARTIFACT_DIRECTORIES = {
    "本実験": "full_4d35fa98_e4a41f40",
    "期間感度評価": "duration_54f94fee_e4a41f40",
}
EVALUATION9_DIRECTORY_DEFAULT_VERSION = "2026-09-30-fable5-artifacts"
EVALUATION10_DIRECTORY_DEFAULT_VERSION = "2026-09-30-current-snapshot"


def render_sensor_representation(scope: str) -> tuple[str, str, str]:
    """Return representation, namespaced dataset, and its default sensor-map path."""
    representation = st.selectbox(
        "センサ表現",
        SENSOR_REPRESENTATIONS,
        index=SENSOR_REPRESENTATIONS.index(DEFAULT_SENSOR_REPRESENTATION),
        format_func=lambda value: (
            "個別センサ（既定・34特徴量）"
            if value == "individual"
            else "部屋統合（従来・10特徴量）"
        ),
        key=f"{scope}_sensor_representation",
        help="個別センサと部屋統合では代表状態・LLM出力を別の成果物パスへ保存します。",
    )
    dataset = artifact_dataset_name("aruba", representation)
    map_path = sensor_map_path(PROJECT_ROOT, representation)
    return representation, dataset, rel_default(map_path)


def model_results_relative(common: dict | None = None) -> str:
    """Return the selected model's result root relative to the project."""
    root = (
        Path(common["model_results_root"])
        if common and common.get("model_results_root")
        else current_model_results_root()
    )
    return root.relative_to(PROJECT_ROOT).as_posix()


def eval5_condition_widget_key(
    field: str,
    *,
    model_id: str,
    dataset: str,
    n_states: int,
    hamming_threshold: int,
    days: int,
) -> str:
    """Keep Evaluation 5 path widgets scoped to the selected condition."""
    suffix = short_suffix(n_states, hamming_threshold, days)
    return f"eval5_{field}_{model_id}_{dataset}_{suffix}"


def model_output_relative(common: dict | None = None) -> str:
    root = (
        Path(common["model_output_root"])
        if common and common.get("model_output_root")
        else current_model_output_root()
    )
    return root.relative_to(PROJECT_ROOT).as_posix()


def evaluation9_directory_defaults(common: dict, preset: str) -> tuple[str, str]:
    """Return resume-safe Evaluation 9 directories for the selected preset."""
    directory_name = preset_directory_name(preset)
    if common.get("model_id") == FABLE5_MODEL_ID:
        directory_name = FABLE5_EVALUATION9_ARTIFACT_DIRECTORIES.get(
            preset, directory_name
        )
    return (
        f"{model_output_relative(common)}/9_hestia/{directory_name}",
        f"{model_results_relative(common)}/9_hestia/{directory_name}",
    )


def evaluation10_directory_defaults(common: dict, snapshot_name: str) -> tuple[str, str]:
    """Keep Evaluation 10 pointed at the selected snapshot's formal namespace."""
    directory_name = f"10_real_home_temporal_generalization/{snapshot_name}"
    return (
        f"{model_output_relative(common)}/{directory_name}",
        f"{model_results_relative(common)}/{directory_name}",
    )


def evaluation10_artifact_status(output_dir: Path, results_dir: Path) -> tuple[bool, int, int]:
    """Return preparation, complete-run, and per-mode checkpoint availability."""
    complete_runs = list(results_dir.glob("llm/*/llm_sequences_modes_*.json"))
    mode_checkpoints = list(results_dir.glob("llm/*/llm_mode_records_run*/*.json"))
    return (output_dir.joinpath("preparation.json").is_file(), len(complete_runs), len(mode_checkpoints))


def log_root(settings: dict) -> Path:
    """Keep dashboard histories and logs with the model that produced them."""
    return Path(settings["model_output_root"]) / "logs" / "evaluation_dashboard"

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
        "files": "evaluation9_duration_summary.csv",
        "how_to_read": "train_days別にoverallと6 conditionを比較します。14日差分は同じseed同士のpaired差です。canonical goldが期間ごとに変わるため、exact-match F1だけでなくADL macro-F1とtest coverageも併読します。",
    },
    {
        "files": "evaluation9_summary.csv",
        "how_to_read": "condition・method別にcomplete/missing/invalidとcomplete_seedsを先に確認します。回収率、対象活動coverage、Other時間割合、ADL macro-F1の平均・標本標準偏差を読みます。1seedの標準偏差は空欄です。",
    },
    {
        "files": "evaluation9_summary.json",
        "how_to_read": "runsでseed・反復別のstatus、理由、指標・採点コードhashを確認します。欠落を0点にせず、不完全なseedを主集計から除外します。頻度対照のADL指標はnullです。",
    },
]
RESULT_FILE_ORDER["評価9"] = [
    "evaluation9_summary.csv",
    "evaluation9_summary.json",
    "evaluation9_duration_summary.csv",
    "evaluation9_duration_summary.json",
]

RESULT_GUIDES["評価10"] = [
    {
        "files": "evaluation10_summary.csv",
        "how_to_read": "methodごとに5 runのcomplete数、FRR、日単位再現率、遷移被覆率の平均と標本標準偏差を読みます。不足runは0点ではありません。",
    },
    {
        "files": "evaluation10_summary_by_run.csv, evaluation10_pattern_details.csv, evaluation10_by_time_band.csv, evaluation10_by_pattern_length.csv",
        "how_to_read": "run別のFRR、系列・時間帯ごとの出現、時間帯別・系列長別の再現率と平均test supportを確認します。",
    },
    {
        "files": "evaluation10_summary.json",
        "how_to_read": "入力hash、manifest timezone、前半/後半の半開区間、K/h/平滑化と警告を確認します。正解ADLがないためADL精度ではありません。",
    },
]
RESULT_FILE_ORDER["評価10"] = [
    "evaluation10_summary.csv",
    "evaluation10_summary_by_run.csv",
    "evaluation10_by_time_band.csv",
    "evaluation10_by_pattern_length.csv",
    "evaluation10_pattern_details.csv",
    "evaluation10_manifest.json",
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


def model_environment_preview(settings: dict) -> str:
    overrides = settings.get("model_environment", {})
    return " ".join(f"{key}={value}" for key, value in sorted(overrides.items()))


def common_sidebar() -> dict:
    st.sidebar.header("共通設定")
    evaluation = st.sidebar.radio(
        "評価・テストを選択",
        ["評価4", "評価5", "評価6", "評価7", "評価8", "評価9", "評価10", "APIテスト"],
        horizontal=True,
    )
    model_id = st.sidebar.selectbox(
        "実行LLMモデル",
        [model.model_id for model in DASHBOARD_MODELS],
        index=[model.model_id for model in DASHBOARD_MODELS].index(
            DEFAULT_DASHBOARD_MODEL_ID
        ),
        format_func=lambda value: dashboard_model(value).label,
        help="選択値はこの画面が起動する評価プロセスだけに渡されます。.env は変更しません。",
    )
    model = dashboard_model(model_id)
    model_root = model.results_root(PROJECT_ROOT)
    model_output = model.output_root(PROJECT_ROOT)
    st.sidebar.caption(
        f"保存先: `{display_path(model_output)}`, `{display_path(model_root)}` / provider: `{model.provider}`"
    )
    runner = st.sidebar.selectbox("Python実行方法", ["uv run python", "python"], index=0)
    run_name = st.sidebar.text_input("run名（ログ用）", "manual")
    smoothing_window_sec = st.sidebar.number_input(
        "チャタリング除去時間（秒）",
        min_value=0,
        value=SMOOTHING_WINDOW_SEC,
        step=1,
        help="同じセンサの遅延OFF窓幅です。0で無効化します。",
        disabled=evaluation in {"評価9", "APIテスト"},
    )
    dry_run = st.sidebar.checkbox("dry-run（実行せずコマンドだけ記録）", value=False)
    st.sidebar.caption(
        "秒数を変更して既存条件を作り直す場合は「全ステップを再実行」を選んでください。"
        "現在の成果物名には秒数が含まれません。"
    )
    if evaluation == "評価9":
        st.sidebar.caption(
            "評価9のseedとLLM run数は評価9画面で編集できます。"
            "日数・平滑化は選択した実験planを使い、共通の平滑化設定は適用しません。"
        )
    elif evaluation != "APIテスト":
        st.sidebar.caption("seed / overwrite は既存CLI引数がないためUI化していません。")
    return {
        "evaluation": evaluation,
        "runner": runner,
        "run_name": run_name,
        "smoothing_window_sec": int(smoothing_window_sec),
        "dry_run": dry_run,
        "dataset": "aruba",
        "model_id": model.model_id,
        "model_label": model.label,
        "model_results_root": str(model_root),
        "model_output_root": str(model_output),
        "model_environment": model.environment_overrides(),
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

    representation, dataset, default_sensor_map = render_sensor_representation("eval4")
    default_state = default_state_table(dataset, int(n_states), int(hamming), int(days))
    model_root = Path(common["model_results_root"])
    model_key = common["model_id"]
    default_patterns = default_proposed_path(
        dataset, int(n_states), int(hamming), int(days), results_root=model_root
    )

    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    sensor_map = st.text_input("センサーマップ", default_sensor_map, key=f"eval4_sensor_map_{representation}")
    state_table = st.text_input("代表状態テーブル", rel_default(default_state), key=f"eval4_state_table_{representation}")
    patterns = st.text_input(
        "評価対象パターンJSON",
        rel_default(default_patterns),
        key=f"eval4_patterns_{model_key}_{representation}",
    )
    state_series = st.text_input("既存state_series CSV（任意）", "", key=f"eval4_state_series_{representation}")
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
    default_eval4_output = f"{model_results_relative(common)}/4_adl_detect"
    if representation != "room":
        default_eval4_output += f"_{representation}"
    output_dir = st.text_input(
        "output-dir",
        default_eval4_output,
        key=f"eval4_output_dir_{model_key}_{representation}",
    )
    default_eval4_state_series = f"{model_output_relative(common)}/4_adl_detect"
    if representation != "room":
        default_eval4_state_series += f"_{representation}"
    write_state = st.text_input(
        "write-state-series",
        f"{default_eval4_state_series}/state_series.csv",
        key=f"eval4_write_state_series_{model_key}_{representation}",
    )

    return {
        **common,
        "days": int(days),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "sensor_representation": representation,
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

    representation, dataset, default_sensor_map = render_sensor_representation("eval5")
    suffix = short_suffix(int(n_states), int(hamming), int(days))

    def condition_widget_key(field: str) -> str:
        return eval5_condition_widget_key(
            field,
            model_id=common["model_id"],
            dataset=dataset,
            n_states=int(n_states),
            hamming_threshold=int(hamming),
            days=int(days),
        )
    default_eval5_intermediate = (
        f"{model_output_relative(common)}/5_adl_evaluation_{suffix}_fixed"
        if dataset == "aruba"
        else f"{model_output_relative(common)}/5_adl_evaluation_{dataset}_{suffix}_fixed"
    )
    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    state_series = st.text_input(
        "state-series",
        f"{default_eval5_intermediate}/state_series_220days.csv",
        key=condition_widget_key("state_series"),
    )
    state_table = st.text_input(
        "代表状態テーブル",
        rel_default(default_state_table(dataset, int(n_states), int(hamming), int(days))),
        key=condition_widget_key("state_table"),
    )
    sensor_map = st.text_input("センサーマップ", default_sensor_map, key=f"eval5_sensor_map_{representation}")
    patterns_frequency = st.text_input(
        "patterns-frequency",
        f"{model_output_relative(common)}/{dataset}_{suffix}/state_sequence_counts_{suffix}.json",
        key=condition_widget_key("frequency"),
    )
    patterns_rule_light = st.text_input("patterns-rule-light", f"{model_output_relative(common)}/5_rule_filter/frequency_rule_light.csv")
    patterns_rule_medium = st.text_input("patterns-rule-medium", f"{model_output_relative(common)}/5_rule_filter/frequency_rule_medium.csv")
    patterns_rule_strong = st.text_input("patterns-rule-strong", f"{model_output_relative(common)}/5_rule_filter/frequency_rule_strong.csv")
    model_root = Path(common["model_results_root"])
    model_key = common["model_id"]
    patterns_proposed = st.text_input(
        "patterns-proposed",
        rel_default(
            default_proposed_path(
                dataset, int(n_states), int(hamming), int(days), results_root=model_root
            )
        ),
        key=condition_widget_key("patterns_proposed"),
    )
    with st.expander("複数run用テンプレート（任意）"):
        st.caption("使用可能: {dataset}, {n_states}, {hamming_threshold}, {hamming}, {days}, {run}, {suffix}")
        patterns_proposed_template = st.text_input(
            "patterns-proposed-template",
            "",
            placeholder=(
                f"{model_results_relative(common)}/{dataset}_{{suffix}}/"
                "llm_sequences_modes_{suffix}_{run}.json"
            ),
            key=condition_widget_key("patterns_template"),
        )
        skip_missing_runs = st.checkbox("skip-missing-runs", value=False)
        proposed_base_path = PROJECT_ROOT / patterns_proposed if not Path(patterns_proposed).is_absolute() else Path(patterns_proposed)
        expected_run_paths = [
            proposed_run_path(
                proposed_base_path,
                patterns_proposed_template,
                dataset,
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
            (
                f"{model_output_relative(common)}/5_adl_correspondence_baselines_fixed"
                if dataset == "aruba"
                else f"{model_output_relative(common)}/5_adl_correspondence_baselines_{representation}_fixed"
            ),
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
    default_eval5_output = f"{model_results_relative(common)}/5_pattern_quality_fixed"
    if representation != "room":
        default_eval5_output = f"{model_results_relative(common)}/5_pattern_quality_{representation}_fixed"
    output_dir = st.text_input(
        "output-dir",
        default_eval5_output,
        key=f"eval5_output_dir_{model_key}_{representation}",
    )

    return {
        **common,
        "days": int(days),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "sensor_representation": representation,
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
    comparison_track = st.radio(
        "比較トラック",
        ["full_pipeline", "strict_ablation"],
        format_func=lambda value: "Full-pipeline comparison" if value == "full_pipeline" else "Strict Ablation comparison",
        horizontal=True,
    )
    st.caption(
        "既定は holdout: 先頭14日で生成し、Day 155–220 を独立テストとして採点します。"
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        days = st.number_input("使用日数", min_value=1, value=14, step=1)
    with col2:
        n_states = st.number_input("代表状態数 K", min_value=1, value=DEFAULT_N_STATES, step=1)
    with col3:
        hamming = st.number_input("ハミング距離閾値", min_value=0, value=DEFAULT_HAMMING_THRESHOLD, step=1)
    with col4:
        runs = st.number_input("runs", min_value=1, value=5, step=1)

    representation, dataset, default_sensor_map = render_sensor_representation("eval6")
    suffix = short_suffix(int(n_states), int(hamming), int(days))
    default_intermediate = (
        f"{model_output_relative(common)}/6_adl_evaluation_{suffix}"
        if dataset == "aruba"
        else f"{model_output_relative(common)}/6_adl_evaluation_{dataset}_{suffix}"
    )
    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    sensor_map = st.text_input("センサーマップ", default_sensor_map, key=f"eval6_sensor_map_{representation}")
    state_table = st.text_input("代表状態テーブル", rel_default(default_state_table(dataset, int(n_states), int(hamming), int(days))), key=f"eval6_state_table_{representation}")
    model_root = Path(common["model_results_root"])
    model_key = common["model_id"]
    proposed = st.text_input(
        "patterns-proposed",
        rel_default(
            default_proposed_path(
                dataset, int(n_states), int(hamming), int(days), results_root=model_root
            )
        ),
        key=f"eval6_patterns_proposed_{model_key}_{representation}",
    )
    llm_only_time_mode = st.radio(
        "LLM-only input",
        options=["split", "legacy"],
        format_func=lambda value: (
            "Split by time period (default)" if value == "split" else "Legacy unsplit"
        ),
        horizontal=True,
        help="splitはMorning / Daytime / Night / Midnightごとに独立してLLMへ入力します。",
    )
    direct = st.text_input(
        "patterns-direct",
        rel_default(
            default_direct_path(
                dataset,
                int(n_states),
                int(hamming),
                int(days),
                results_root=model_root,
                llm_only_time_mode=llm_only_time_mode,
            )
        ),
        key=(
            f"eval6_patterns_direct_{model_key}_{representation}_{llm_only_time_mode}"
        ),
    )
    state_series = st.text_input("state-series", f"{default_intermediate}/state_series.csv", key=f"eval6_state_series_{representation}")
    adl_intervals = st.text_input("adl-intervals（任意。なければlabeled-casasから生成）", f"{model_output_relative(common)}/adl_label_intervals.csv")

    selected_manifest = (
        PROJECT_ROOT
        / model_results_relative(common)
        / "7_param_search_14d_5runs_individual_holdout"
        / "evaluation7_best_condition_manifest.json"
    )
    sol_manifest = (
        PROJECT_ROOT
        / "results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout"
        / "evaluation7_best_condition_manifest.json"
    )
    strict_manifest_default = selected_manifest
    if comparison_track == "strict_ablation" and not selected_manifest.is_file() and sol_manifest.is_file():
        strict_manifest_default = sol_manifest

    with st.expander("複数run用テンプレート（任意）"):
        proposed_template = st.text_input("patterns-proposed-template", "")
        direct_template = st.text_input("patterns-direct-template", "")
        best_condition_manifest = st.text_input(
            "evaluation7 best-condition manifest" + ("（必須）" if comparison_track == "strict_ablation" else "（任意）"),
            rel_default(strict_manifest_default) if comparison_track == "strict_ablation" else "",
            help="Strict Ablationでは唯一の条件源です。選定元モデルと生成モデルが異なる場合も、manifestのK/hを固定して記録します。",
        )

    if comparison_track == "strict_ablation":
        manifest_candidate = Path(best_condition_manifest).expanduser()
        if not manifest_candidate.is_absolute():
            manifest_candidate = PROJECT_ROOT / manifest_candidate
        if not manifest_candidate.is_file():
            st.error(f"Strict Ablation用の評価7 manifestが見つかりません: {display_path(manifest_candidate)}")
            st.stop()
        if manifest_candidate.resolve() != selected_manifest.resolve():
            st.info(
                "評価7で選定した条件はGPT-5.6 Solのmanifestから読み、"
                f"今回のStrict出力は{common['model_label']}の名前空間へ保存します。"
            )

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
    intermediate_dir = st.text_input("中間output-dir", default_intermediate, key=f"eval6_intermediate_{representation}")
    default_eval6_output = f"{model_results_relative(common)}/6_adl_match"
    if representation != "room":
        default_eval6_output += f"_{representation}"
    default_eval6_output += "_holdout_test"
    if llm_only_time_mode == "split":
        default_eval6_output += "_direct_time_split"
    output_dir = st.text_input(
        "比較output-dir",
        default_eval6_output,
        key=f"eval6_output_dir_{model_key}_{representation}_{llm_only_time_mode}",
    )

    return {
        **common,
        "days": int(days),
        "n_states": int(n_states),
        "hamming_threshold": int(hamming),
        "sensor_representation": representation,
        "runs": int(runs),
        "labeled_casas": labeled,
        "sensor_map": sensor_map,
        "state_table": state_table,
        "patterns_proposed": proposed,
        "patterns_direct": direct,
        "llm_only_time_mode": llm_only_time_mode,
        "patterns_proposed_template": proposed_template,
        "patterns_direct_template": direct_template,
        "best_condition_manifest": best_condition_manifest,
        "comparison_track": comparison_track,
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
        "split_mode": "holdout",
        "generation_days": int(days),
        "validation_start_day": 15,
        "validation_end_day": 154,
        "test_start_day": 155,
        "test_end_day": 220,
    }


def render_eval7_settings(common: dict) -> dict:
    st.subheader("評価7: 14日・全28条件・各5 runのパラメータ感度分析")
    st.caption(
        "正式条件は固定です: "
        f"days={FORMAL_EVALUATION7_DAYS}, "
        f"K={','.join(str(value) for value in FORMAL_EVALUATION7_N_STATES)}, "
        f"hamming={','.join(str(value) for value in FORMAL_EVALUATION7_HAMMING)}, "
        f"runs={FORMAL_EVALUATION7_RUNS}。"
    )
    st.caption("既定は holdout: Day 15–154 のvalidationでK,hを選びます。")
    days = FORMAL_EVALUATION7_DAYS
    n_states_list = list(FORMAL_EVALUATION7_N_STATES)
    hamming_thresholds = list(FORMAL_EVALUATION7_HAMMING)

    representation, dataset, default_sensor_map = render_sensor_representation("eval7")
    st.markdown("**入力パス**")
    labeled = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
    sensor_map = st.text_input("センサーマップ", default_sensor_map, key=f"eval7_sensor_map_{representation}")
    adl_intervals = st.text_input("adl-intervals（任意。labeled-casasが存在すればそちらを優先）", f"{model_output_relative(common)}/adl_label_intervals.csv")
    with st.expander("条件別パステンプレート（任意）"):
        st.caption("使用可能: {dataset}, {n_states}, {hamming_threshold}, {hamming}, {days}, {run}, {suffix}")
        patterns_template = st.text_input(
            "patterns-template",
            "",
            placeholder=(
                f"{model_results_relative(common)}/{dataset}_{{suffix}}/"
                "llm_sequences_modes_{suffix}_{run}.json"
            ),
            key=f"eval7_patterns_template_{common['model_id']}_{representation}",
        )
        state_series_template = st.text_input(
            "state-series-template",
            "",
            placeholder=(
                f"{model_output_relative(common)}/6_adl_evaluation_{{suffix}}/state_series.csv"
                if dataset == "aruba"
                else f"{model_output_relative(common)}/6_adl_evaluation_aruba_individual_{{suffix}}/state_series.csv"
            ),
            key=f"eval7_state_series_template_{representation}",
        )

    st.markdown("**評価パラメータ**")
    col1, col2, col3 = st.columns(3)
    with col1:
        runs = FORMAL_EVALUATION7_RUNS
        st.caption("全28条件についてrun 1〜5を生成し、各条件ごとに平均と標準偏差を算出します。")
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
    skip_missing_conditions = st.checkbox("skip-missing-conditions", value=False)
    show_preparation_steps = st.checkbox("不足ファイル作成ステップを表示", value=True)

    st.markdown("**出力**")
    default_eval7_output = f"{model_results_relative(common)}/{FORMAL_EVALUATION7_RESULTS_DIRNAME}"
    if representation != "room":
        default_eval7_output += f"_{representation}"
    default_eval7_output += "_holdout"
    output_dir = st.text_input(
        "output-dir",
        default_eval7_output,
        key=f"eval7_output_dir_{common['model_id']}_{representation}",
    )

    return {
        **common,
        "days": int(days),
        "n_states_list": n_states_list,
        "hamming_thresholds": hamming_thresholds,
        "runs": int(runs),
        "sensor_representation": representation,
        "staged_search": False,
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
        "split_mode": "holdout",
        "generation_days": int(days),
        "validation_start_day": 15,
        "validation_end_day": 154,
        "test_start_day": 155,
        "test_end_day": 220,
    }


def render_api_smoke_test_settings(common: dict) -> dict:
    """Render the standalone one-request API response-format test."""
    st.subheader("APIテスト: 1条件 × 1 run × 1時間帯の疎通・JSON形式確認")
    st.warning(
        "実APIを1回だけ呼びます。正式な評価4〜10、一括実行、通常checkpointには含まれません。"
    )
    st.caption(
        "通常の提案手法抽出と同じプロンプト／LLM adapterを使い、retryなしで初回応答を検証します。"
    )
    smoke_col1, smoke_col2, smoke_col3 = st.columns(3)
    with smoke_col1:
        smoke_n_states = st.selectbox(
            "テスト用 K",
            list(FORMAL_EVALUATION7_N_STATES),
            index=list(FORMAL_EVALUATION7_N_STATES).index(15),
        )
    with smoke_col2:
        smoke_hamming = st.selectbox(
            "テスト用 hamming",
            list(FORMAL_EVALUATION7_HAMMING),
            index=0,
        )
    with smoke_col3:
        smoke_mode = st.selectbox("テスト用時間帯", ["Morning", "Daytime", "Night", "Midnight"])
    smoke_output_dir = st.text_input(
        "APIテスト出力ディレクトリ",
        (
            f"{model_results_relative(common)}/api_smoke_tests/"
            f"aruba_{smoke_n_states}_{smoke_hamming}_{FORMAL_EVALUATION7_DAYS}days/"
            f"{smoke_mode}_{now_stamp()}"
        ),
        key=(
            f"api_smoke_output_{common['model_id']}_{smoke_n_states}_"
            f"{smoke_hamming}_{smoke_mode}"
        ),
    )
    smoke_test_allow_api = st.checkbox(
        "APIテストの1リクエストを許可（費用が発生します）",
        value=False,
    )
    return {
        **common,
        "smoke_test_days": FORMAL_EVALUATION7_DAYS,
        "smoke_test_n_states": int(smoke_n_states),
        "smoke_test_hamming_threshold": int(smoke_hamming),
        "smoke_test_mode": smoke_mode,
        "smoke_test_output_dir": smoke_output_dir,
        "smoke_test_allow_api": smoke_test_allow_api,
    }


def evaluation8_scope_config(scope_label: str) -> tuple[str, int]:
    """Map current and persisted Evaluation 8 labels to a CLI scope."""
    if scope_label.startswith("154日"):
        return "proposed_154days", 154
    if scope_label.startswith("30日"):
        return "comparison_30days", 30
    return "comparison_14days", 14


def evaluation8_comparison_default_paths(
    common: dict,
    n_states: int,
    hamming_threshold: int,
    days: int,
) -> tuple[str, str]:
    """Return canonical Full-pipeline inputs for the formal Evaluation 8 comparison."""
    if (n_states, hamming_threshold, days) != (
        DEFAULT_N_STATES,
        DEFAULT_HAMMING_THRESHOLD,
        14,
    ):
        return "", ""
    dataset = artifact_dataset_name("aruba", DEFAULT_SENSOR_REPRESENTATION)
    suffix = short_suffix(n_states, hamming_threshold, days)
    details = (
        f"{model_results_relative(common)}/"
        "6_adl_match_individual_holdout_test_direct_time_split/"
        "evaluation6_pattern_set_details_by_method.csv"
    )
    state_series = (
        f"{model_output_relative(common)}/6_adl_evaluation_{dataset}_{suffix}/state_series.csv"
    )
    return details, state_series


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
        comparison_details_default, comparison_state_series_default = (
            evaluation8_comparison_default_paths(
                common,
                int(n_states),
                int(hamming),
                days,
            )
        )
        details = st.text_input(
            "evaluation6 details file path",
            comparison_details_default,
            key=f"eval8_details_{common['model_id']}_{suffix}",
        )
        patterns_proposed = ""
        state_series = st.text_input(
            "state-series（評価8でown-ID出現数を再構築）",
            comparison_state_series_default,
            key=f"eval8_state_series_{common['model_id']}_{suffix}",
        )
        labeled_casas = ""
        adl_intervals = ""
        output_dir = st.text_input(
            "output directory",
            f"{model_results_relative(common)}/8_vs_llm_own_id_fixed",
            key=f"eval8_output_comparison_{common['model_id']}",
        )
        st.caption(
            "正式な14日比較は、K=10・h=2・個別センサのFull-pipeline評価6成果物を既定にします。"
            "他の条件では、対応する評価6詳細CSVとstate-seriesを明示指定してください。"
        )
        patterns_proposed_template = ""
        runs = 5
    else:
        details = ""
        patterns_proposed = st.text_input(
            "patterns-proposed (154日)",
            f"{model_results_relative(common)}/aruba_{suffix}/llm_sequences_modes_{suffix}_1.json",
            key=f"eval8_patterns_proposed_{common['model_id']}",
        )
        state_series_default = (
            f"{model_output_relative(common)}/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv"
            if (int(n_states), int(hamming)) == (DEFAULT_N_STATES, DEFAULT_HAMMING_THRESHOLD)
            else ""
        )
        state_series = st.text_input("state-series (154日)", state_series_default)
        if not state_series_default:
            st.caption("Kまたはハミング距離を変更した場合は、その条件で作成した154日state-series CSVを指定してください。")
        labeled_casas = st.text_input("ラベル付きCASAS", "new_labeled_data/aruba.txt")
        adl_intervals = st.text_input("adl-intervals（任意）", f"{model_output_relative(common)}/adl_label_intervals.csv")
        patterns_proposed_template = st.text_input(
            "patterns-proposed-template（任意）",
            "",
            placeholder=(
                f"{model_results_relative(common)}/aruba_15_0_154days/"
                "llm_sequences_modes_15_0_154days_{run}.json"
            ),
            key=f"eval8_patterns_template_{common['model_id']}",
        )
        output_dir = st.text_input(
            "output directory",
            f"{model_results_relative(common)}/8_proposed_own_id_fixed",
            key=f"eval8_output_proposed_{common['model_id']}",
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
    st.info(
        "Pilot / 本実験・小規模確認 / 本実験 / 期間感度評価の既存planを基準に、"
        "seedとLLM run数だけを変更できます。研究指標や条件定義は変わりません。"
    )
    archive_notice = st.session_state.pop("eval9_archive_notice", None)
    if archive_notice:
        st.success(f"既存成果物をバックアップしました: `{archive_notice}`")
    render_hestia_house_connections()
    hestia_root = st.text_input("Hestiaディレクトリ", "Hestia")
    resolved_hestia = Path(hestia_root).expanduser()
    if not resolved_hestia.is_absolute():
        resolved_hestia = PROJECT_ROOT / resolved_hestia
    preset = st.selectbox("実験プリセット", list(PRESET_PLAN_FILENAMES), key="eval9_preset")
    try:
        base_plan_path, base_plan = load_preset_plan(resolved_hestia, preset)
    except (OSError, ValueError) as exc:
        st.error(f"実験planを読み込めません: {exc}")
        st.stop()
        raise RuntimeError("Streamlit execution did not stop") from exc
    duration = preset == DURATION_PRESET
    duration_train_days = DURATION_TRAIN_DAYS if duration else None

    preset_token = (
        f"{base_plan_path.resolve()}:{preset}:{common['model_id']}:"
        f"{EVALUATION9_DIRECTORY_DEFAULT_VERSION}"
    )
    if st.session_state.get("eval9_loaded_preset") != preset_token:
        st.session_state["eval9_loaded_preset"] = preset_token
        st.session_state["eval9_llm_runs"] = base_plan.llm_runs
        st.session_state["eval9_seeds"] = ", ".join(str(seed) for seed in base_plan.seeds)
        experiment_default, output_default = evaluation9_directory_defaults(common, preset)
        st.session_state["eval9_experiment"] = experiment_default
        st.session_state["eval9_output_dir"] = output_default

    st.caption(f"ベースplan: `{display_path(base_plan_path)}`")
    summary_columns = st.columns(4)
    summary_columns[0].metric("conditions", len(base_plan.conditions))
    summary_columns[1].metric("train / test", f"{base_plan.train_days}日 / {base_plan.test_days}日")
    summary_columns[2].metric("seeds", str(base_plan.seeds))
    summary_columns[3].metric("llm_runs", base_plan.llm_runs)
    if duration:
        st.info(
            "train期間: 3 / 7 / 14 / 28日、比較基準: 14日、test期間: 7日固定。"
            "同一condition・seedの35日rawログを共有し、Day 29〜35を共通testにします。"
        )
        duration_workers = st.number_input(
            "期間ごとの並列数",
            min_value=1,
            max_value=len(DURATION_TRAIN_DAYS),
            value=len(DURATION_TRAIN_DAYS),
            step=1,
            help=(
                "prepare・頻度対照・LLM抽出を期間ごとに並列実行します。"
                "API利用時は同時リクエスト数も増えるため、利用枠に応じて下げてください。"
            ),
        )
        st.caption(
            "rawログ生成と最終集計は1回ずつ実行し、各工程は全期間の完了後に次へ進みます。"
        )
    else:
        duration_workers = 1

    llm_runs = st.number_input(
        "LLM run数",
        min_value=1,
        step=1,
        key="eval9_llm_runs",
        help="同一condition・seedについてLLM抽出を繰り返す回数です。",
    )
    seeds_text = st.text_input(
        "seed一覧（整数・カンマ区切り）",
        key="eval9_seeds",
        help="再現性のためseed値を明示します。値の自動生成は行いません。",
    )
    try:
        seeds = parse_seed_list(seeds_text)
        effective_plan = build_effective_plan(
            base_plan, seeds=seeds, llm_runs=int(llm_runs)
        )
    except ValueError as exc:
        st.error(f"実行設定が不正です: {exc}")
        st.stop()
        raise RuntimeError("Streamlit execution did not stop") from exc
    st.caption(f"Seed数: {len(effective_plan.seeds)}")

    experiment = st.text_input(
        "生成ログ・中間成果物ディレクトリ", key="eval9_experiment"
    )
    output_dir = st.text_input("評価9の集計先", key="eval9_output_dir")
    effective_plan_path = save_effective_plan(
        effective_plan,
        Path(common["model_output_root"]) / "logs" / "evaluation_dashboard" / "evaluation9_plans",
    )
    st.caption(f"実行用plan: `{effective_plan_path.relative_to(PROJECT_ROOT)}`")

    resolved_experiment = Path(experiment).expanduser()
    if not resolved_experiment.is_absolute():
        resolved_experiment = PROJECT_ROOT / resolved_experiment
    resolved_output_dir = Path(output_dir).expanduser()
    if not resolved_output_dir.is_absolute():
        resolved_output_dir = PROJECT_ROOT / resolved_output_dir
    scale = estimate_scale(
        effective_plan,
        experiment=resolved_experiment,
        duration_train_days=duration_train_days,
    )
    st.markdown("#### 実行規模")
    scale_columns = st.columns(5)
    scale_columns[0].metric("condition数", scale.condition_count)
    scale_columns[1].metric("seed数", scale.seed_count)
    scale_columns[2].metric("LLM runs", scale.llm_runs)
    scale_columns[3].metric("時間帯数", scale.time_band_count)
    scale_columns[4].metric("Hestia生成run数", scale.hestia_run_count)
    budget_label = "推定API呼び出し（残り）" if scale.uses_existing_budget else "推定API呼び出し"
    st.metric(budget_label, f"{scale.fresh_api_calls}回")
    st.caption(
        f"{scale.condition_count} conditions × {scale.seed_count} seeds × "
        f"{scale.llm_runs} LLM runs × {scale.time_band_count} time bands"
        + (f" × {len(DURATION_TRAIN_DAYS)} train durations。" if duration else "。")
        + f"JSON parse retryを含む上限は{scale.parse_attempts_upper_bound}回です。"
    )
    if scale.uses_existing_budget:
        st.caption(
            f"既存checkpointを反映したextraction_budgetです（全件未実行なら{scale.full_fresh_api_calls}回）。"
        )
    else:
        st.caption("すべて未実行の場合の推定です。既存checkpointがあれば実際の呼び出しは減ります。")
    st.caption("backendのtransport retryによる追加通信は正確に予測できないため、この上限には含みません。")
    snapshot_matches = experiment_snapshot_matches(
        effective_plan,
        resolved_experiment,
        duration_train_days=duration_train_days,
    )
    preparation_matches = preparation_provenance_matches(resolved_experiment)
    if snapshot_matches is False or preparation_matches is False:
        plan_hash = effective_plan_path.stem.rsplit("_", 1)[-1][:8]
        directory_name = preset_directory_name(preset)
        suggested_suffix = plan_hash
        if preparation_matches is False:
            provenance_suffix = current_preparation_provenance_suffix()
            if provenance_suffix is not None:
                suggested_suffix = f"{plan_hash}_{provenance_suffix}"
        suggested_experiment = f"{model_output_relative(common)}/9_hestia/{directory_name}_{suggested_suffix}"
        suggested_output = (
            f"{model_results_relative(common)}/9_hestia/{directory_name}_{suggested_suffix}"
        )

        def use_suggested_eval9_directories() -> None:
            st.session_state["eval9_experiment"] = suggested_experiment
            st.session_state["eval9_output_dir"] = suggested_output

        if snapshot_matches is False:
            st.error(
                "選択した実行用planが、この実験ディレクトリのexperiment.jsonと一致しません。"
                "既存のhash検証を回避せず、新しい実験ディレクトリを指定してください。"
            )
        else:
            st.error(
                "既存の前処理成果物は現在の研究コード／設定の指紋と一致しません。"
                "Hestiaの再現性検証を回避せず、新しい実験ディレクトリを指定してください。"
            )
        st.info(
            "例: 生成ログ・中間成果物ディレクトリを "
            f"`{suggested_experiment}`、評価9の集計先を "
            f"`{suggested_output}` に変更してください。"
        )
        st.button(
            "推奨する新しい出力先へ切り替える",
            key="eval9_use_suggested_directories",
            type="primary",
            on_click=use_suggested_eval9_directories,
        )
        st.markdown("**同じ出力先を再利用する場合**")
        archive_confirmed = st.checkbox(
            "既存の生成・集計成果物をバックアップへ移動することを確認しました",
            key="eval9_confirm_archive",
        )
        if common["dry_run"]:
            st.caption("dry-run中は成果物のバックアップ操作を実行しません。")
        if st.button(
            "既存成果物をバックアップして同じ出力先を再利用",
            key="eval9_archive_and_reuse",
            disabled=not archive_confirmed or common["dry_run"],
        ):
            try:
                archive = archive_evaluation9_outputs(
                    experiment=resolved_experiment,
                    output_dir=resolved_output_dir,
                    project_root=PROJECT_ROOT,
                    archive_root=Path(common["model_output_root"])
                    / "logs"
                    / "evaluation_dashboard"
                    / "evaluation9_backups",
                )
            except (OSError, ValueError) as exc:
                st.error(f"バックアップできませんでした: {exc}")
            else:
                archive_directory = str(archive["archive_directory"])
                append_history(
                    log_root(common),
                    {
                        "evaluation": common["evaluation"],
                        "action": "archive_outputs_for_compatibility_change",
                        "experiment": str(resolved_experiment),
                        "output_dir": output_dir,
                        "archive_directory": archive_directory,
                    },
                )
                st.session_state["eval9_archive_notice"] = display_path(
                    Path(archive_directory)
                )
                st.rerun()
        st.stop()

    method = st.selectbox("採点する手法", ["both", "frequency", "llm"])
    allow_api = st.checkbox("LLM抽出のAPI呼出しを許可（費用が発生します）", value=False)
    if not allow_api:
        st.success("API許可OFF: この設定変更および実行ではGemini APIを呼びません（0回）。")
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
        "plan": str(base_plan_path),
        "effective_plan": str(effective_plan_path),
        "preset": preset,
        "seeds": effective_plan.seeds,
        "llm_runs": effective_plan.llm_runs,
        "experiment": experiment,
        "output_dir": output_dir,
        "method": method,
        "allow_api": allow_api,
        "duration": duration,
        "duration_train_days": list(DURATION_TRAIN_DAYS) if duration else [],
        "duration_workers": int(duration_workers),
    }


def render_eval10_settings(common: dict) -> dict:
    st.subheader("評価10: SwitchBot実宅ログの将来再現性評価")
    st.caption("時系列の前半だけで状態表・STN・LLM入力を固定し、後半で同じ時間帯の完全一致再出現を評価します。正解ADL精度ではありません。")
    snapshot = st.text_input(
        "SwitchBotスナップショット",
        "data/switchbot/2026-08-19_2026-09-19",
    )
    snapshot_name = Path(snapshot.rstrip("/")).name or "snapshot"
    output_default, results_default = evaluation10_directory_defaults(
        common, snapshot_name
    )
    eval10_directory_token = (
        f"{common['model_id']}:{snapshot_name}:{EVALUATION10_DIRECTORY_DEFAULT_VERSION}"
    )
    if st.session_state.get("eval10_loaded_snapshot") != eval10_directory_token:
        st.session_state["eval10_loaded_snapshot"] = eval10_directory_token
        st.session_state["eval10_output_dir"] = output_default
        st.session_state["eval10_results_dir"] = results_default

    def use_current_eval10_directories() -> None:
        st.session_state["eval10_output_dir"] = output_default
        st.session_state["eval10_results_dir"] = results_default

    resolved_output_default = PROJECT_ROOT / output_default
    resolved_results_default = PROJECT_ROOT / results_default
    has_preparation, complete_runs, mode_checkpoints = evaluation10_artifact_status(
        resolved_output_default, resolved_results_default
    )
    if has_preparation or complete_runs or mode_checkpoints:
        st.info(
            "現在のsnapshotの既存成果物を検出: "
            f"前処理={'あり' if has_preparation else 'なし'}、"
            f"完了LLM run={complete_runs}/5、"
            f"時間帯チェックポイント={mode_checkpoints}件。"
        )
    st.button(
        "現在のsnapshotの既存成果物パスへ戻す",
        key="eval10_use_current_directories",
        on_click=use_current_eval10_directories,
    )
    output_dir = st.text_input(
        "中間成果物ディレクトリ", key="eval10_output_dir"
    )
    results_dir = st.text_input(
        "評価10の正式集計先",
        key="eval10_results_dir",
    )
    eval7_best_condition_manifest = FORMAL_EVALUATION7_BEST_CONDITION_MANIFEST.as_posix()
    st.caption(
        "評価7の最適条件manifest（K/h固定）: "
        f"`{eval7_best_condition_manifest}`"
    )
    train_ratio = st.number_input(
        "学習期間比率", min_value=0.1, max_value=0.9, value=0.7, step=0.1
    )
    st.info("K=10、h=2 は評価7のmanifestからのみ読込みます。LLM抽出は固定で5 runです。")
    split_at = st.text_input("テスト開始（任意・現地時刻の0時）", "")
    sampling_seconds = st.number_input("サンプリング間隔（秒）", min_value=1, value=1, step=1)
    min_sequence_length = st.number_input("最小系列長", min_value=2, value=2, step=1)
    max_sequence_length = st.number_input(
        "最大系列長", min_value=int(min_sequence_length), value=max(4, int(min_sequence_length)), step=1
    )
    min_train_occurrences = st.number_input("学習側の最小出現回数", min_value=1, value=2, step=1)
    top_k_per_mode = st.number_input("時間帯ごとの最大頻出系列数", min_value=1, value=20, step=1)
    method = st.selectbox("採点する手法", ["llm", "both", "frequency"])
    overwrite_results = st.checkbox(
        "既存の評価10集計CSV/JSONを上書きする",
        value=False,
        help=(
            "ステップ3の集計結果だけを置き換えます。前処理・LLM run JSON・"
            "時間帯checkpointは変更せず、Bedrock APIも呼びません。"
        ),
    )
    if overwrite_results:
        st.warning(
            "既存の評価10集計CSV/JSONをこの設定・既存LLM runで置き換えます。"
            "前の集計値が必要なら先に別場所へ保存してください。"
        )
    allow_api = st.checkbox("LLM抽出のAPI呼出しを許可（費用が発生します）", value=False)
    if allow_api:
        st.warning("一括実行またはステップ2でBedrock APIを5 run分呼びます。")
    return {
        **common,
        "snapshot": snapshot,
        "output_dir": output_dir,
        "results_dir": results_dir,
        "eval7_best_condition_manifest": eval7_best_condition_manifest,
        "split_at": split_at,
        "train_ratio": float(train_ratio),
        "runs": 5,
        "smoothing_window_sec": SMOOTHING_WINDOW_SEC,
        "sampling_seconds": int(sampling_seconds),
        "min_sequence_length": int(min_sequence_length),
        "max_sequence_length": int(max_sequence_length),
        "min_train_occurrences": int(min_train_occurrences),
        "top_k_per_mode": int(top_k_per_mode),
        "method": method,
        "overwrite_results": overwrite_results,
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
        st.caption(
            f"実行LLM: {settings['model_label']} / {model_environment_preview(settings)}"
        )
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
            selected_log_root = log_root(settings)
            log_dir = ensure_log_dir(selected_log_root, settings["evaluation"], settings["run_name"])
            log_path = log_dir / f"{step.step_id}.log"
            record = {
                "evaluation": settings["evaluation"],
                "step_id": step.step_id,
                "title": step.title,
                "dry_run": settings["dry_run"],
                "command": step.command,
                "command_preview": command_preview(step.command),
                "model_id": settings["model_id"],
                "model_label": settings["model_label"],
                "model_environment": settings["model_environment"],
                "log_path": display_path(log_path),
            }
            append_history(selected_log_root, record)
            if settings["dry_run"]:
                log_path.write_text(
                    f"# 実行環境: {model_environment_preview(settings)}\n"
                    f"$ {command_preview(step.command)}\n",
                    encoding="utf-8",
                )
                st.info(f"dry-runとして記録しました: {display_path(log_path)}")
                return

            output_box = st.empty()

            def update_output(text: str) -> None:
                output_box.text_area("実行ログ", text, height=320)

            with st.spinner("実行中..."):
                result = run_command(
                    step.command,
                    cwd=PROJECT_ROOT,
                    log_path=log_path,
                    on_output=update_output,
                    environment_overrides=settings["model_environment"],
                )
            if result.returncode == 0:
                st.success(f"成功: {result.elapsed_seconds:.1f}s / log: {display_path(result.log_path)}")
            else:
                st.error(f"失敗: exit={result.returncode} / {result.elapsed_seconds:.1f}s / log: {display_path(result.log_path)}")
                st.text_area("ログ末尾", result.output[-8000:], height=260)


def render_llm_response_smoke_test(settings: dict) -> None:
    """Render the separately opted-in, one-request LLM response check."""
    st.markdown("### API疎通・JSON形式テスト")
    step = build_llm_response_smoke_test_step(settings)
    st.warning(
        "このテストは評価4〜10の実験・一括実行には含めません。"
        "指定した1時間帯に対して実APIを1回だけ呼びます。"
    )
    if not settings["smoke_test_allow_api"]:
        st.info(
            "API許可OFF: コマンドは実行できません。上のチェックボックスで1リクエストを明示許可してください。"
        )
        st.code(command_preview(step.command), language="bash")
        return

    render_step(step, settings)
    validation_path = step.expected_outputs[0]
    if validation_path.exists():
        try:
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        st.markdown("**直近の形式検証結果**")
        st.json(validation)


FINAL_EVALUATION_STEP_IDS = {
    "eval4_evaluate",
    "eval5_evaluate",
    "eval6_compare",
    "eval6_strict_evaluate",
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


def batch_progress_text(completed: int, total: int, current_title: str | None = None) -> str:
    """Return the user-visible whole-batch progress label."""
    base = f"進捗: {completed}/{total} ステップ完了"
    return f"{base} / 実行中: {current_title}" if current_title else base


def batch_declared_output_paths(steps: list[EvaluationStep]) -> set[str]:
    return {str(path.resolve()) for step in steps for path in step.expected_outputs}


def conflicting_active_batch_outputs(steps: list[EvaluationStep]) -> list[Path]:
    requested = batch_declared_output_paths(steps)
    if not requested:
        return []
    active_outputs = {
        str(path)
        for _, status in discover_batch_statuses(PROJECT_ROOT / "output")
        if status.get("status") in ACTIVE_BATCH_STATUSES
        for path in status.get("declared_output_paths", [])
    }
    return [Path(path) for path in sorted(requested & active_outputs)]


@st.fragment(run_every=2)
def render_background_batch_monitor() -> None:
    """Keep task progress visible while the user configures another evaluation."""
    statuses = discover_batch_statuses(PROJECT_ROOT / "output")
    active = [(path, status) for path, status in statuses if status.get("status") in ACTIVE_BATCH_STATUSES]
    finished = recent_finished_batches(PROJECT_ROOT / "output")
    if not active and not finished:
        return

    st.markdown("### バックグラウンド一括実行")
    st.caption("約2秒ごとに更新します。評価を切り替えても、開始済みの一括実行は継続します。中断は実行中の評価コマンドも停止します。")
    for status_path, status in active:
        completed = int(status.get("completed_steps", 0))
        total = max(int(status.get("total_steps", 0)), 1)
        current_title = status.get("current_step_title")
        label = batch_progress_text(completed, total, str(current_title) if current_title else None)
        progress_column, cancel_column = st.columns([5, 1])
        with progress_column:
            st.progress(completed / total, text=label)
            st.caption(
                f"{status.get('evaluation', '評価')} / {status.get('model_label', 'モデル未設定')} / "
                f"状態: {status.get('status')} / 管理ファイル: {display_path(status_path)}"
            )
        with cancel_column:
            if st.button(
                "中断",
                key=f"cancel_background_batch_{status_path}",
                type="secondary",
                help="この一括実行と、現在実行中の評価コマンドを停止します。",
                use_container_width=True,
            ):
                cancelled, message = request_batch_cancellation(status_path)
                if cancelled:
                    st.success(message)
                else:
                    st.warning(message)

    if finished:
        st.markdown("#### 最近終了した一括実行")
        st.caption("直近5件を表示します。失敗時は停止したステップとログを確認できます。")
    for status_path, status in finished:
        state = str(status.get("status", "unknown"))
        completed = int(status.get("completed_steps", 0))
        total = max(int(status.get("total_steps", 0)), 1)
        summary = (
            f"{status.get('evaluation', '評価')} / {status.get('model_label', 'モデル未設定')} / "
            f"{completed}/{total} ステップ / 終了: {status.get('finished_at', '不明')}"
        )
        if state == "succeeded":
            st.success(f"完了: {summary}")
        elif state == "cancelled":
            st.warning(f"中断: {summary}")
        else:
            stopped_step = next(
                (
                    step
                    for step in status.get("steps", [])
                    if step.get("status") in {"failed", "blocked_missing_inputs"}
                ),
                {},
            )
            detail = str(stopped_step.get("title", "不明なステップ"))
            returncode = stopped_step.get("returncode")
            if returncode is not None:
                detail += f"（終了コード {returncode}）"
            st.error(f"失敗: {summary} / 停止: {detail}")
            if log_path := stopped_step.get("log_path"):
                st.caption(f"失敗ログ: {display_path(Path(str(log_path)))}")
        st.caption(f"管理ファイル: {display_path(status_path)}")


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

    conflicts = conflicting_active_batch_outputs(targets)
    if conflicts:
        st.error("同じ出力先を使う一括実行がすでに動作中です。完了後に開始してください。")
        st.code("\n".join(display_path(path) for path in conflicts), language="text")
        return

    selected_log_root = log_root(settings)
    log_dir = ensure_log_dir(selected_log_root, settings["evaluation"], f"{settings['run_name']}_batch")
    plan_path = log_dir / "batch_plan.json"
    planned_steps = [
        {
            "index": index,
            "step_id": step.step_id,
            "title": step.title,
            "command": step.command,
            "required_inputs": [str(path) for path in step.required_inputs],
            "log_path": str(log_dir / f"{index:02d}_{step.step_id}.log"),
        }
        for index, step in enumerate(targets, start=1)
    ]
    plan = {
        "evaluation": settings["evaluation"],
        "model_id": settings["model_id"],
        "model_label": settings["model_label"],
        "batch_mode": mode,
        "dry_run": settings["dry_run"],
        "project_root": str(PROJECT_ROOT),
        "log_root": str(selected_log_root),
        "model_environment": settings["model_environment"],
        "declared_output_paths": sorted(batch_declared_output_paths(targets)),
        "steps": planned_steps,
    }
    status_path = create_batch_artifacts(plan_path, plan)
    worker = launch_batch_worker(plan_path, log_dir / "batch_worker.log")
    st.success(
        f"バックグラウンドで開始しました（PID: {worker.pid}）。評価を切り替えても継続します。"
    )
    st.info(f"一括実行ログ: {display_path(log_dir)} / 状態: {display_path(status_path)}")


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


def reviewer_response_result_dirs() -> list[Path]:
    """Find completed read-only reviewer-response result bundles."""
    root = PROJECT_ROOT / "results" / "gpt-5.6-sol" / "reviewer_response"
    if not root.exists():
        return []
    return sorted(
        {
            path.parent
            for path in root.rglob("reviewer_response_evaluation_summary.json")
            if path.name == "reviewer_response_evaluation_summary.json"
        }
    )


def reviewer_table(bundle: Path, name: str) -> pd.DataFrame | None:
    path = bundle / "tables" / name
    return pd.read_csv(path) if path.exists() else None


def render_reviewer_response_results(current_evaluation: str | None) -> None:
    """Render paper-oriented tables and cautious interpretations for Eval 5--10."""
    bundles = reviewer_response_result_dirs()
    if not bundles:
        return
    selected_evaluation = current_evaluation if current_evaluation in {"評価5", "評価6", "評価7", "評価8", "評価9", "評価10"} else None
    heading = f"{selected_evaluation}の査読対応結果" if selected_evaluation else "査読対応版の統合結果"
    st.subheader(heading)
    labels = [display_path(path) for path in bundles]
    selected_label = st.selectbox("査読対応版の結果セット", labels, index=len(labels) - 1)
    bundle = bundles[labels.index(selected_label)]
    summary = json.loads((bundle / "reviewer_response_evaluation_summary.json").read_text(encoding="utf-8"))
    status_rows = [
        {"評価": name, "状態": value["status"], "注記": value["note"]}
        for name, value in summary.get("status", {}).items()
        if selected_evaluation is None or name == selected_evaluation.replace("評価", "eval")
    ]
    st.dataframe(pd.DataFrame(status_rows), hide_index=True, use_container_width=True)

    def show(evaluation: str) -> bool:
        return selected_evaluation is None or selected_evaluation == evaluation

    if show("評価5"):
        st.markdown("### パターン品質")
    eval5 = reviewer_table(bundle, "table_eval5_pattern_quality.csv")
    if show("評価5") and eval5 is not None:
        st.dataframe(eval5, hide_index=True, use_container_width=True)
        proposed = eval5[eval5["method"] == "proposed"]
        if not proposed.empty:
            row = proposed.iloc[0]
            st.markdown(
                "**考察**\n"
                f"- 提案法は平均 {row['pattern_count']} patterns、test-supported rate は {row['test_supported_rate']} で、生成系列の大半は後続期間にも出現しました。\n"
                "- このsupportは系列の再出現であり、ADL解釈の正しさそのものを示す指標ではありません。\n"
                f"- fragmentation は {row['fragmentation']}（N/A run: {row['n_a_runs']}）です。比較可能な短系列・長系列pairがないため、断片化抑制を実証したとは主張しません。\n"
                "- redundancyは完全一致する `(time band, normalized sequence)` の重複だけを数えており、部分系列の断片化とは別の概念です。"
            )

    if show("評価6"):
        st.markdown("### ADL認識とStrict Ablation")
    eval6_full = reviewer_table(bundle, "table_eval6_full_pipeline.csv")
    eval6_strict = reviewer_table(bundle, "table_eval6_strict_ablation.csv")
    if show("評価6"):
        full_tab, strict_tab = st.tabs(["Full-pipeline", "Strict Ablation"])
    else:
        full_tab = strict_tab = None
    if full_tab is not None:
        with full_tab:
            if eval6_full is not None:
                st.dataframe(eval6_full, hide_index=True, use_container_width=True)
                proposed = eval6_full[eval6_full["method"] == "proposed"]
                direct = eval6_full[eval6_full["method"] == "direct_log_baseline"]
                if not proposed.empty and not direct.empty:
                    st.markdown(
                        "**考察**\n"
                        f"- Day155–220 holdoutでProposed F1={proposed.iloc[0]['f1']}、Direct LLM F1={direct.iloc[0]['f1']} です。\n"
                        "- Proposedはprecisionが高く、Direct LLMより少ない不適合ADL集合を出す傾向があります。一方で、これはSTN以外のprompt・処理差も含むシステム全体の比較です。\n"
                        "- STN表現のみの寄与は、隣のStrict Ablationを根拠に判断します。"
                    )
        with strict_tab:
            if eval6_strict is not None:
                st.dataframe(eval6_strict, hide_index=True, use_container_width=True)
                proposed = eval6_strict[eval6_strict["method"] == "proposed"]
                if not proposed.empty:
                    st.markdown(
                        "**考察**\n"
                        f"- 共通完了runは {proposed.iloc[0]['common_runs']}、ProposedのF1={proposed.iloc[0]['f1']}、paired Delta F1={proposed.iloc[0]['paired_delta_f1']} です。\n"
                        "- Strict条件では入力代表状態系列、prompt、schema、postprocessingを揃えているため、この差はSTN表現の有無に対応します。\n"
                        "- CIは既存成果物にepisode単位の再標本化単位がないため表示しません。5 run平均だけをブートストラップして有意性を装うことは避けます。"
                    )

    if show("評価7"):
        st.markdown("### K / h 感度")
    eval7 = reviewer_table(bundle, "table_eval7_sensitivity.csv")
    if show("評価7") and eval7 is not None:
        st.dataframe(eval7, hide_index=True, use_container_width=True)
        best = eval7.iloc[0]
        st.markdown(
            "**考察**\n"
            f"- validation上の最良条件は K={best['K']}, h={best['h']}、F1={best['f1']} です。\n"
            "- 上位近傍条件も表で比較できます。最良点だけでなく近傍設定の値を確認し、設定依存性の強さを判断してください。\n"
            "- この表はDay15–154 validationのみで作成されており、Day155–220 testをK/h選択に使用していません。"
        )
        figure = bundle / "figures" / "eval7_sensitivity_heatmap.png"
        if figure.exists():
            st.image(str(figure), caption="K / h validation F1", use_container_width=True)

    if show("評価8"):
        st.markdown("### 頻度層別")
    eval8 = reviewer_table(bundle, "table_eval8_frequency.csv")
    if show("評価8") and eval8 is not None:
        st.dataframe(eval8, hide_index=True, use_container_width=True)
        st.markdown(
            "**考察**\n"
            "- ProposedとDirect LLMに同一のfixed frequency binを適用しているため、帯ごとの数値は直接比較できます。\n"
            "- 中高頻度帯のF1は、繰り返し十分に観測される系列で解釈が安定するかを示します。\n"
            "- 空bin、N/A、または `runs_with_patterns` が少ない帯は推定が不安定です。帯ごとの優劣を一般化する根拠にはしません。\n"
            "- これはFull-pipelineの頻度層別結果であり、Strict Ablationの帯別比較ではありません。"
        )
        figure = bundle / "figures" / "eval8_frequency_f1.png"
        if figure.exists():
            st.image(str(figure), caption="Frequency-stratified F1", use_container_width=True)

    if show("評価9"):
        st.markdown("### Hestia頑健性")
    eval9 = reviewer_table(bundle, "table_eval9_robustness.csv")
    if show("評価9") and eval9 is not None:
        st.dataframe(eval9, hide_index=True, use_container_width=True)
        overall = eval9[eval9["condition"] == "overall"]
        if not overall.empty:
            row = overall.iloc[0]
            st.markdown(
                "**考察**\n"
                f"- 14日学習・3 seedのoverall sequence F1={row['f1']}、episode coverage={row['episode_coverage']}、fragmentation={row['fragmentation']} です。\n"
                "- 条件別の値は、住宅レイアウトと生活変動への感度を示します。Aruba単独の結果を一般化する十分な証拠にはなりません。\n"
                "- 既存Hestia scorerはsequence指標を出力しており、ADL JaccardはN/Aです。指標の意味をArubaのADL F1と混同しません。\n"
                "- 低いF1は、合成環境への移植性に限界があるという反証的な結果として報告すべきです。"
            )
        figure = bundle / "figures" / "eval9_hestia_f1.png"
        if figure.exists():
            st.image(str(figure), caption="Hestia condition F1", use_container_width=True)

    if show("評価10"):
        st.markdown("### 実宅の時間的汎化")
    eval10 = reviewer_table(bundle, "table_eval10_real_home.csv")
    if show("評価10") and eval10 is not None:
        st.dataframe(eval10, hide_index=True, use_container_width=True)
        overall = eval10[eval10["scope"] == "overall"]
        if not overall.empty:
            row = overall.iloc[0]
            st.markdown(
                "**考察**\n"
                f"- chronological holdoutで平均抽出数={row['extracted']}、再出現数={row['recurrent']}、FRR={row['frr']} です。\n"
                "- 抽出パターン数が少ないため、FRRは少数のパターンに左右されます。生活変動だけでなく観測期間の短さも考慮が必要です。\n"
                "- 同じ時間帯での完全系列一致だけを再出現と数えています。これは将来再現性の厳しい診断です。\n"
                "- 完全なADL Ground Truthがないため、ADL認識精度や提案法の正確性を示す結果ではありません。"
            )
        figure = bundle / "figures" / "eval10_time_band_frr.png"
        if figure.exists():
            st.image(str(figure), caption="Future recurrence by time band", use_container_width=True)

    structural = reviewer_table(bundle, "table_structural_validity.csv")
    if show("評価6") and structural is not None:
        st.markdown("### Structural Validity")
        st.dataframe(structural, hide_index=True, use_container_width=True)
        st.warning("既存成果物に互換な制約検証結果がないため、旧称Groundednessを根拠なく表示していません。")

    if selected_evaluation is None:
        human = summary.get("human_evaluation", {})
        st.markdown("### Human Evaluation")
        st.info(
            f"blind sample: {human.get('sample_count', 0)} items / status: {human.get('status', 'unknown')}。"
            "評価者向けアイテムにはmethod名とrun IDを含めません。"
        )


def render_results(default_dirs: list[Path], current_evaluation: str | None = None) -> None:
    st.subheader("結果表示")
    render_reviewer_response_results(current_evaluation)
    if reviewer_response_result_dirs():
        st.divider()
        st.markdown("### 個別ファイル・過去runの比較")
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
        if selected_file.name == "evaluation9_duration_summary.csv":
            llm_rows = df[df["method"] == "llm"] if "method" in df.columns else df
            available = sorted(llm_rows["condition"].dropna().unique())
            selected_conditions = st.multiselect(
                "期間感度で表示するcondition",
                available,
                default=[value for value in available if value == "overall"] or available[:1],
            )
            for metric in (
                "adl_macro_f1_mean",
                "test_target_episode_coverage_mean",
                "f1_mean",
            ):
                if metric in llm_rows.columns and selected_conditions:
                    chart = (
                        llm_rows[llm_rows["condition"].isin(selected_conditions)]
                        .pivot(index="train_days", columns="condition", values=metric)
                        .sort_index()
                    )
                    st.markdown(f"**{metric}**")
                    st.line_chart(chart)
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


def render_logs(common: dict) -> None:
    st.subheader("ログ確認")
    selected_log_root = log_root(common)
    records = load_history(selected_log_root)
    if not records:
        st.info("まだコマンド履歴がありません。")
        return
    df = pd.DataFrame(records)
    st.dataframe(df, use_container_width=True)
    log_files = sorted(selected_log_root.rglob("*.log")) if selected_log_root.exists() else []
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
    if evaluation == "APIテスト":
        return [PROJECT_ROOT / settings["smoke_test_output_dir"]]
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
    st.caption("評価4〜10、APIテスト、Hestia Studioを1つにまとめたローカル研究Webアプリです。")

    common = common_sidebar()
    run_tab, studio_tab, result_tab, log_tab = st.tabs(
        ["ステップ実行", "Hestia Studio", "結果比較", "ログ確認"]
    )

    with run_tab:
        render_background_batch_monitor()
        if common["evaluation"] == "APIテスト":
            settings = render_api_smoke_test_settings(common)
            steps = []
        elif common["evaluation"] == "評価4":
            settings = render_eval4_settings(common)
            steps = build_evaluation4_steps(settings)
        elif common["evaluation"] == "評価5":
            settings = render_eval5_settings(common)
            steps = build_evaluation5_steps(settings)
        elif common["evaluation"] == "評価6":
            settings = render_eval6_settings(common)
            steps = (
                build_evaluation6_strict_ablation_steps(settings)
                if settings["comparison_track"] == "strict_ablation"
                else build_evaluation6_steps(settings)
            )
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

        st.info(
            f"この評価のLLM: {common['model_label']}。中間生成物・ログは "
            f"`{model_output_relative(common)}/`、LLM出力と評価結果は "
            f"`{model_results_relative(common)}/` に分離して保存します。"
        )
        st.markdown("### ステップ")
        if common["evaluation"] == "APIテスト":
            render_llm_response_smoke_test(settings)
        else:
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
        render_logs(common)


if __name__ == "__main__":
    main()
