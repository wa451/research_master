"""Command builders for the local evaluation dashboard.

The dashboard intentionally stays a thin wrapper around the existing CLI
entry points. This module only translates UI settings into subprocess argv.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex
from typing import Any

from experiment_config import SMOOTHING_WINDOW_SEC
from src.behavior_pattern_mining.evaluation.evaluation7_staged import (
    select_top_condition_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class EvaluationStep:
    step_id: str
    title: str
    description: str
    command: list[str]
    required_inputs: list[Path] = field(default_factory=list)
    expected_outputs: list[Path] = field(default_factory=list)


def as_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def command_preview(command: list[str]) -> str:
    return shlex.join([str(part) for part in command])


def runner_parts(runner: str) -> list[str]:
    return shlex.split(runner.strip())


def script_cmd(runner: str, script: str) -> list[str]:
    return [*runner_parts(runner), script]


def add_arg(command: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and value == "":
        return
    command.extend([flag, str(value)])


def add_multi_arg(command: list[str], flag: str, values: list[Any] | tuple[Any, ...]) -> None:
    cleaned = [str(value) for value in values if str(value) != ""]
    if cleaned:
        command.append(flag)
        command.extend(cleaned)


def add_flag(command: list[str], flag: str, enabled: bool) -> None:
    if enabled:
        command.append(flag)


def condition_suffix(dataset: str, n_states: int, hamming_threshold: int, days: int) -> str:
    return f"{dataset}_{n_states}_{hamming_threshold}_{days}days"


def short_suffix(n_states: int, hamming_threshold: int, days: int) -> str:
    return f"{n_states}_{hamming_threshold}_{days}days"


def default_proposed_path(dataset: str, n_states: int, hamming_threshold: int, days: int, run: int = 1) -> Path:
    suffix = short_suffix(n_states, hamming_threshold, days)
    return PROJECT_ROOT / "output" / f"{dataset}_{suffix}" / f"llm_sequences_modes_{suffix}_{run}.json"


def default_state_table(dataset: str, n_states: int, hamming_threshold: int, days: int) -> Path:
    return PROJECT_ROOT / "state" / f"{dataset}_{short_suffix(n_states, hamming_threshold, days)}.txt"


def default_direct_path(n_states: int, hamming_threshold: int, days: int, run: int = 1) -> Path:
    return PROJECT_ROOT / "output" / f"llm_direct_{n_states}_{hamming_threshold}_{days}days" / f"{run}.json"


def default_eval_state_series_path(n_states: int, hamming_threshold: int, days: int) -> Path:
    if n_states == 15 and hamming_threshold == 1 and days in {14, 30}:
        return PROJECT_ROOT / "output" / f"6_adl_evaluation_{days}" / "state_series.csv"
    return PROJECT_ROOT / "output" / f"6_adl_evaluation_{short_suffix(n_states, hamming_threshold, days)}" / "state_series.csv"


def template_path(template: str, dataset: str, n_states: int, hamming_threshold: int, days: int, run: int | None = None) -> Path:
    suffix = short_suffix(n_states, hamming_threshold, days)
    values = {
        "dataset": dataset,
        "n_states": n_states,
        "hamming_threshold": hamming_threshold,
        "hamming": hamming_threshold,
        "days": days,
        "suffix": suffix,
    }
    if run is not None:
        values["run"] = run
    return as_path(template.format(**values)) or PROJECT_ROOT


def proposed_run_path(
    base_path: Path,
    template: str | None,
    dataset: str,
    n_states: int,
    hamming_threshold: int,
    days: int,
    run: int,
) -> Path:
    if template:
        return template_path(template, dataset, n_states, hamming_threshold, days, run=run)
    if run == 1:
        return base_path
    stem = base_path.stem
    suffix = base_path.suffix
    prefix, sep, last = stem.rpartition("_")
    if sep and last.isdigit():
        return base_path.with_name(f"{prefix}_{run}{suffix}")
    return base_path.with_name(f"{stem}_{run}{suffix}")


def build_evaluation4_steps(settings: dict[str, Any]) -> list[EvaluationStep]:
    runner = settings["runner"]
    dataset = settings["dataset"]
    days = settings["days"]
    n_states = settings["n_states"]
    hamming = settings["hamming_threshold"]
    labeled = as_path(settings["labeled_casas"])
    sensor_map = as_path(settings["sensor_map"])
    state_table = as_path(settings["state_table"])
    patterns = as_path(settings["patterns"])
    output_dir = as_path(settings["output_dir"])
    write_state_series = as_path(settings["write_state_series"])
    state_series = as_path(settings.get("state_series"))
    event_log = as_path(settings.get("event_log"))

    build_cmd = script_cmd(runner, "scripts/run_build_network_from_labeled_casas.py")
    add_arg(build_cmd, "--labeled-casas", labeled)
    add_arg(build_cmd, "--sensor-map", sensor_map)
    add_arg(build_cmd, "--days", days)
    add_arg(build_cmd, "--n-states", n_states)
    add_arg(build_cmd, "--hamming-threshold", hamming)
    add_arg(
        build_cmd,
        "--smoothing-window-sec",
        settings.get("smoothing_window_sec", SMOOTHING_WINDOW_SEC),
    )

    llm_cmd = script_cmd(runner, "scripts/run_llm_extraction.py")
    add_arg(llm_cmd, "--days", days)
    add_arg(llm_cmd, "--n-states", n_states)
    add_arg(llm_cmd, "--hamming-threshold", hamming)

    eval_cmd = script_cmd(runner, "scripts/evaluate_adl_labels.py")
    add_arg(eval_cmd, "--labeled-casas", labeled)
    add_arg(eval_cmd, "--state-series", state_series)
    add_arg(eval_cmd, "--event-log", event_log)
    add_arg(eval_cmd, "--state-table", state_table)
    add_arg(eval_cmd, "--sensor-map", sensor_map)
    add_arg(eval_cmd, "--patterns", patterns)
    add_arg(eval_cmd, "--output-dir", output_dir)
    add_multi_arg(eval_cmd, "--iou-thresholds", settings["iou_thresholds"])
    add_arg(eval_cmd, "--wake-window-minutes", settings["wake_window_minutes"])
    add_arg(eval_cmd, "--match-mode", settings["match_mode"])
    add_arg(eval_cmd, "--max-skip-duration-minutes", settings["max_skip_duration_minutes"])
    add_arg(eval_cmd, "--hamming-threshold", hamming)
    add_arg(eval_cmd, "--split-date", settings.get("split_date"))
    add_arg(eval_cmd, "--train-ratio", settings.get("train_ratio"))
    add_arg(eval_cmd, "--write-state-series", write_state_series)
    add_arg(eval_cmd, "--merge-gap-minutes", settings["merge_gap_minutes"])
    add_arg(eval_cmd, "--min-duration-config", as_path(settings.get("min_duration_config")))
    add_arg(eval_cmd, "--hit-tolerance-minutes", settings["hit_tolerance_minutes"])

    expected_eval_outputs = [
        output_dir / "pattern_occurrences.csv",
        output_dir / "pattern_adl_mapping.csv",
        output_dir / "merged_predictions.csv",
        output_dir / "filtered_predictions.csv",
        output_dir / "adl_interval_hit_metrics.csv",
        output_dir / "evaluation_summary.json",
    ]
    for threshold in settings["iou_thresholds"]:
        expected_eval_outputs.append(output_dir / f"adl_metrics_iou_{threshold}.csv")
        expected_eval_outputs.append(output_dir / f"boundary_metrics_iou_{threshold}.csv")
    if write_state_series is not None:
        expected_eval_outputs.append(write_state_series)

    return [
        EvaluationStep(
            "eval4_build_network",
            "1. 代表状態・状態遷移ネットワークを作成",
            "state table と picture/* の状態遷移JSONを作成します。既にある場合はスキップ可能です。",
            build_cmd,
            [p for p in [labeled, sensor_map] if p is not None],
            [state_table, PROJECT_ROOT / "picture" / condition_suffix(dataset, n_states, hamming, days) / "state_transition_all.json"],
        ),
        EvaluationStep(
            "eval4_llm",
            "2. 提案手法LLMパターンを抽出",
            "状態遷移ネットワークから LLM JSON を生成します。APIキーを使う重い処理です。",
            llm_cmd,
            [PROJECT_ROOT / "picture" / condition_suffix(dataset, n_states, hamming, days) / "state_transition_all.json"],
            [patterns],
        ),
        EvaluationStep(
            "eval4_evaluate",
            "3. 評価4を実行",
            "ADL区間との照合、IoU評価、境界評価、state_series出力を行います。",
            eval_cmd,
            [p for p in [labeled, state_table, sensor_map, patterns, state_series, event_log] if p is not None],
            expected_eval_outputs,
        ),
    ]


def build_evaluation5_steps(settings: dict[str, Any]) -> list[EvaluationStep]:
    runner = settings["runner"]
    dataset = settings["dataset"]
    days = settings["days"]
    n_states = settings["n_states"]
    hamming = settings["hamming_threshold"]
    runs = settings.get("runs", 1)
    labeled = as_path(settings["labeled_casas"])
    state_series = as_path(settings["state_series"])
    intermediate_output_dir = as_path(
        settings.get("eval5_intermediate_output_dir")
        or settings.get("eval4_output_dir")
        or "output/5_adl_evaluation"
    )
    state_table = as_path(settings["state_table"])
    sensor_map = as_path(settings["sensor_map"])
    proposed = as_path(settings["patterns_proposed"])
    proposed_template = settings.get("patterns_proposed_template")
    output_dir = as_path(settings["output_dir"])
    transition_json = PROJECT_ROOT / "picture" / condition_suffix(dataset, n_states, hamming, days) / "state_transition_all.json"

    build_cmd = script_cmd(runner, "scripts/run_build_network_from_labeled_casas.py")
    add_arg(build_cmd, "--labeled-casas", labeled)
    add_arg(build_cmd, "--sensor-map", sensor_map)
    add_arg(build_cmd, "--days", days)
    add_arg(build_cmd, "--n-states", n_states)
    add_arg(build_cmd, "--hamming-threshold", hamming)
    add_arg(
        build_cmd,
        "--smoothing-window-sec",
        settings.get("smoothing_window_sec", SMOOTHING_WINDOW_SEC),
    )

    llm_cmd = script_cmd(runner, "scripts/run_llm_extraction.py")
    add_arg(llm_cmd, "--days", days)
    add_arg(llm_cmd, "--n-states", n_states)
    add_arg(llm_cmd, "--hamming-threshold", hamming)
    add_arg(llm_cmd, "--runs", runs)

    prep_cmd = script_cmd(runner, "scripts/evaluate_adl_labels.py")
    add_arg(prep_cmd, "--labeled-casas", labeled)
    add_arg(prep_cmd, "--state-table", state_table)
    add_arg(prep_cmd, "--sensor-map", sensor_map)
    add_arg(prep_cmd, "--patterns", proposed)
    add_arg(prep_cmd, "--output-dir", intermediate_output_dir)
    add_arg(prep_cmd, "--write-state-series", state_series)

    eval_cmd = script_cmd(runner, "scripts/evaluate_adl_correspondence.py")
    add_arg(eval_cmd, "--labeled-casas", labeled)
    add_arg(eval_cmd, "--state-series", state_series)
    pattern_flags = {
        "--patterns-frequency": as_path(settings["patterns_frequency"]),
        "--patterns-rule-light": as_path(settings["patterns_rule_light"]),
        "--patterns-rule-medium": as_path(settings["patterns_rule_medium"]),
        "--patterns-rule-strong": as_path(settings["patterns_rule_strong"]),
        "--patterns-proposed": proposed,
    }
    for flag, path in pattern_flags.items():
        add_arg(eval_cmd, flag, path)
    add_arg(eval_cmd, "--output-dir", output_dir)
    add_arg(eval_cmd, "--wake-window-minutes", settings["wake_window_minutes"])
    add_arg(eval_cmd, "--match-mode", settings["match_mode"])
    add_arg(eval_cmd, "--max-skip-duration-minutes", settings["max_skip_duration_minutes"])
    add_arg(eval_cmd, "--train-ratio", settings["train_ratio"])
    add_arg(eval_cmd, "--train-start-date", settings.get("train_start_date"))
    add_arg(eval_cmd, "--train-end-date", settings.get("train_end_date"))
    add_arg(eval_cmd, "--test-start-date", settings.get("test_start_date"))
    add_arg(eval_cmd, "--test-end-date", settings.get("test_end_date"))
    add_arg(eval_cmd, "--min-overlap-seconds", settings["min_overlap_seconds"])
    add_arg(eval_cmd, "--grounded-hit-threshold", settings["grounded_hit_threshold"])
    add_arg(eval_cmd, "--grounded-purity-threshold", settings["grounded_purity_threshold"])
    add_arg(eval_cmd, "--useless-hit-threshold", settings["useless_hit_threshold"])
    add_arg(eval_cmd, "--useless-purity-threshold", settings["useless_purity_threshold"])
    add_arg(eval_cmd, "--assigned-adl-purity-threshold", settings["assigned_adl_purity_threshold"])
    add_arg(eval_cmd, "--assigned-adl-max-categories", settings["assigned_adl_max_categories"])
    add_flag(eval_cmd, "--enable-fp-growth-baseline", settings["enable_fp_growth_baseline"])
    add_arg(eval_cmd, "--fp-min-support", settings["fp_min_support"])
    add_arg(eval_cmd, "--fp-top-k", settings["fp_top_k"])
    add_arg(eval_cmd, "--fp-min-len", settings["fp_min_len"])
    add_arg(eval_cmd, "--fp-max-len", settings["fp_max_len"])
    add_arg(eval_cmd, "--fp-max-median-duration-seconds", settings["fp_max_median_duration_seconds"])
    add_arg(eval_cmd, "--fp-max-p90-duration-seconds", settings["fp_max_p90_duration_seconds"])
    add_arg(eval_cmd, "--baseline-cache-dir", as_path(settings["baseline_cache_dir"]))
    if settings.get("use_baseline_cache", True):
        eval_cmd.append("--use-baseline-cache")
    else:
        eval_cmd.append("--no-use-baseline-cache")
    if settings["enable_transition_baseline"]:
        eval_cmd.append("--enable-transition-baseline")
    else:
        eval_cmd.append("--no-enable-transition-baseline")
    add_arg(eval_cmd, "--transition-top-k", settings["transition_top_k"])
    add_arg(eval_cmd, "--transition-min-prob", settings["transition_min_prob"])
    add_arg(eval_cmd, "--transition-min-len", settings["transition_min_len"])
    add_arg(eval_cmd, "--transition-max-len", settings["transition_max_len"])
    add_arg(eval_cmd, "--fragmentation-containment-threshold", settings["fragmentation_containment_threshold"])
    add_arg(eval_cmd, "--low-information-threshold", settings["low_information_threshold"])
    add_arg(eval_cmd, "--patterns-proposed-template", proposed_template)
    add_arg(eval_cmd, "--runs", runs)
    add_flag(eval_cmd, "--skip-missing-runs", settings.get("skip_missing_runs", False))
    add_multi_arg(eval_cmd, "--other-state-labels", settings["other_state_labels"])
    if settings["exclude_other_adl_from_any"]:
        eval_cmd.append("--exclude-other-adl-from-any")
    else:
        eval_cmd.append("--no-exclude-other-adl-from-any")
    add_flag(eval_cmd, "--include-no-test-support-in-denominator", settings["include_no_test_support_in_denominator"])
    add_flag(eval_cmd, "--no-auto-generate-baselines", settings["no_auto_generate_baselines"])

    required_eval_inputs = [labeled, state_series, proposed]
    if runs > 1 and not settings.get("skip_missing_runs", False):
        for run in range(2, runs + 1):
            required_eval_inputs.append(
                proposed_run_path(proposed, proposed_template, dataset, n_states, hamming, days, run)
            )
    if settings["no_auto_generate_baselines"]:
        required_eval_inputs.extend(pattern_flags.values())

    expected_proposed_outputs = [
        proposed_run_path(proposed, proposed_template, dataset, n_states, hamming, days, run)
        for run in range(1, runs + 1)
    ]
    expected_eval_outputs = [
        output_dir / "evaluation5_summary_by_method.csv",
        output_dir / "evaluation5_pattern_details.csv",
        output_dir / "evaluation5_summary.json",
    ]
    if runs > 1 or settings.get("skip_missing_runs", False):
        expected_eval_outputs.insert(1, output_dir / "evaluation5_summary_by_method_by_run.csv")

    return [
        EvaluationStep(
            "eval5_build_network",
            "1. 代表状態・状態遷移ネットワークを作成",
            "評価5条件の state table と状態遷移JSONを作成します。既にある場合は一括実行ではスキップされます。",
            build_cmd,
            [p for p in [labeled, sensor_map] if p is not None],
            [state_table, transition_json],
        ),
        EvaluationStep(
            "eval5_proposed_llm",
            "2. 提案手法LLM出力を生成",
            "状態遷移ネットワークから提案手法の LLM JSON を指定run数分生成します。APIキーを使う重い処理です。",
            llm_cmd,
            [transition_json],
            expected_proposed_outputs,
        ),
        EvaluationStep(
            "eval5_prepare_state_series",
            "3. 評価5用 state_series を作成",
            "評価5専用の中間output-dirへ代表状態系列CSVを作成します。既にある場合は一括実行ではスキップされます。",
            prep_cmd,
            [p for p in [labeled, state_table, sensor_map, proposed] if p is not None],
            [state_series],
        ),
        EvaluationStep(
            "eval5_evaluate",
            "4. 評価5を実行",
            "frequency/rule/FP-Growth/transition_probability/proposed のパターン単位評価を実行します。",
            eval_cmd,
            [p for p in required_eval_inputs if p is not None],
            expected_eval_outputs,
        ),
    ]


def build_evaluation6_steps(settings: dict[str, Any]) -> list[EvaluationStep]:
    runner = settings["runner"]
    dataset = settings["dataset"]
    days = settings["days"]
    n_states = settings["n_states"]
    hamming = settings["hamming_threshold"]
    runs = settings["runs"]
    labeled = as_path(settings["labeled_casas"])
    sensor_map = as_path(settings["sensor_map"])
    state_table = as_path(settings["state_table"])
    proposed = as_path(settings["patterns_proposed"])
    direct = as_path(settings["patterns_direct"])
    state_series = as_path(settings["state_series"])
    intermediate_dir = as_path(settings["intermediate_output_dir"])
    output_dir = as_path(settings["output_dir"])

    build_cmd = script_cmd(runner, "scripts/run_build_network_from_labeled_casas.py")
    add_arg(build_cmd, "--labeled-casas", labeled)
    add_arg(build_cmd, "--sensor-map", sensor_map)
    add_arg(build_cmd, "--days", days)
    add_arg(build_cmd, "--n-states", n_states)
    add_arg(build_cmd, "--hamming-threshold", hamming)
    add_arg(
        build_cmd,
        "--smoothing-window-sec",
        settings.get("smoothing_window_sec", SMOOTHING_WINDOW_SEC),
    )

    proposed_cmd = script_cmd(runner, "scripts/run_llm_extraction.py")
    add_arg(proposed_cmd, "--days", days)
    add_arg(proposed_cmd, "--n-states", n_states)
    add_arg(proposed_cmd, "--hamming-threshold", hamming)
    add_arg(proposed_cmd, "--runs", runs)

    state_series_cmd = script_cmd(runner, "scripts/evaluate_adl_labels.py")
    add_arg(state_series_cmd, "--labeled-casas", labeled)
    add_arg(state_series_cmd, "--state-table", state_table)
    add_arg(state_series_cmd, "--sensor-map", sensor_map)
    add_arg(state_series_cmd, "--patterns", proposed)
    add_arg(state_series_cmd, "--output-dir", intermediate_dir)
    add_arg(state_series_cmd, "--write-state-series", state_series)
    add_arg(state_series_cmd, "--hamming-threshold", hamming)

    direct_cmd = script_cmd(runner, "scripts/run_direct_log_baseline.py")
    add_arg(direct_cmd, "--log-days", days)
    add_arg(direct_cmd, "--state-days", days)
    add_flag(direct_cmd, "--extract-only", True)
    add_arg(direct_cmd, "--n-states", n_states)
    add_arg(direct_cmd, "--hamming-threshold", hamming)
    add_arg(direct_cmd, "--runs", runs)

    compare_cmd = script_cmd(runner, "scripts/evaluate_6_compare_adl_interpretation_set.py")
    add_arg(compare_cmd, "--patterns-proposed", proposed)
    add_arg(compare_cmd, "--patterns-proposed-template", settings.get("patterns_proposed_template"))
    add_arg(compare_cmd, "--patterns-direct", direct)
    add_arg(compare_cmd, "--patterns-direct-template", settings.get("patterns_direct_template"))
    add_arg(compare_cmd, "--state-series", state_series)
    add_arg(compare_cmd, "--adl-intervals", as_path(settings.get("adl_intervals")))
    add_arg(compare_cmd, "--labeled-casas", labeled)
    add_arg(compare_cmd, "--output-dir", output_dir)
    add_arg(compare_cmd, "--min-overlap-ratio-for-true-label", settings["min_overlap_ratio_for_true_label"])
    add_arg(compare_cmd, "--no-overlap-label", settings["no_overlap_label"])
    add_arg(compare_cmd, "--missing-pred-label", settings["missing_pred_label"])
    add_arg(compare_cmd, "--unknown-pred-label", settings["unknown_pred_label"])
    add_arg(compare_cmd, "--wake-window-minutes", settings["wake_window_minutes"])
    add_arg(compare_cmd, "--match-mode", settings["match_mode"])
    add_arg(compare_cmd, "--max-skip-duration-minutes", settings["max_skip_duration_minutes"])
    add_arg(compare_cmd, "--days", days)
    add_arg(compare_cmd, "--n-states", n_states)
    add_arg(compare_cmd, "--hamming-threshold", hamming)
    add_arg(compare_cmd, "--runs", runs)
    add_flag(compare_cmd, "--skip-missing-runs", settings["skip_missing_runs"])

    suffix = short_suffix(n_states, hamming, days)
    final_dir = output_dir if output_dir.name == suffix else output_dir / suffix
    expected_proposed = [default_proposed_path(dataset, n_states, hamming, days, 1)]
    expected_direct = [default_direct_path(n_states, hamming, days, 1)]
    if runs > 1:
        expected_proposed.append(default_proposed_path(dataset, n_states, hamming, days, runs))
        expected_direct.append(default_direct_path(n_states, hamming, days, runs))

    return [
        EvaluationStep(
            "eval6_build_network",
            "1. 14日版の代表状態・状態遷移ネットワークを作成",
            "評価6条件の state table と状態遷移JSONを作成します。",
            build_cmd,
            [p for p in [labeled, sensor_map] if p is not None],
            [state_table, PROJECT_ROOT / "picture" / condition_suffix(dataset, n_states, hamming, days) / "state_transition_all.json"],
        ),
        EvaluationStep(
            "eval6_proposed_llm",
            "2. 提案手法LLM出力を生成",
            "提案手法の LLM JSON を指定run数分生成します。APIキーを使う重い処理です。",
            proposed_cmd,
            [PROJECT_ROOT / "picture" / condition_suffix(dataset, n_states, hamming, days) / "state_transition_all.json"],
            expected_proposed,
        ),
        EvaluationStep(
            "eval6_state_series",
            "3. 評価6用 state_series を作成",
            "評価6比較で両手法に共通利用する代表状態系列CSVを作成します。",
            state_series_cmd,
            [p for p in [labeled, state_table, sensor_map, proposed] if p is not None],
            [state_series, intermediate_dir / "pattern_occurrences.csv"],
        ),
        EvaluationStep(
            "eval6_direct_baseline",
            "4. LLM単独ベースラインを生成",
            "直接ログ入力の LLM JSON を指定run数分生成します。APIキーを使う重い処理です。",
            direct_cmd,
            [p for p in [labeled, state_table] if p is not None],
            expected_direct,
        ),
        EvaluationStep(
            "eval6_compare",
            "5. 評価6の手法間比較を実行",
            "提案手法とLLM単独ベースラインのADL解釈ラベルset一致を比較します。",
            compare_cmd,
            [p for p in [proposed, direct, state_series, labeled] if p is not None],
            [
                final_dir / "evaluation6_method_comparison.csv",
                final_dir / "evaluation6_method_comparison_by_run.csv",
                final_dir / "evaluation6_llm_usage_comparison.csv",
                final_dir / "evaluation6_pattern_set_details_by_method.csv",
                final_dir / "evaluation6_by_pred_label_by_method.csv",
                final_dir / "evaluation6_by_true_label_by_method.csv",
                final_dir / "evaluation6_by_time_band_by_method.csv",
                final_dir / "evaluation6_comparison_summary.json",
            ],
        ),
    ]


def build_evaluation8_steps(settings: dict[str, Any]) -> list[EvaluationStep]:
    """Build either the 14-day comparison or 154-day proposed-only Evaluation 8 command."""
    analysis_scope = settings["analysis_scope"]
    n_states = int(settings["n_states"])
    hamming = int(settings["hamming_threshold"])
    days = int(settings["days"])
    output_dir = as_path(settings["output_dir"])
    if output_dir is None:
        raise ValueError("Evaluation 8 requires an output directory.")

    command = script_cmd(settings["runner"], "scripts/evaluate_8_frequency_stratified_adl_consistency.py")
    add_arg(command, "--analysis-scope", analysis_scope)
    add_arg(command, "--output-dir", output_dir)
    frequency_band_mode = settings["frequency_band_mode"]
    add_arg(command, "--frequency-band-mode", frequency_band_mode)
    if frequency_band_mode in {"fixed", "both"}:
        add_arg(command, "--fixed-frequency-bin-edges", settings["fixed_frequency_bin_edges"])
    add_arg(command, "--n-states", n_states)
    add_arg(command, "--hamming-threshold", hamming)
    add_arg(command, "--days", days)

    if analysis_scope in {"comparison_14days", "comparison_30days"}:
        details = as_path(settings["evaluation6_details"])
        if details is None:
            raise ValueError("Comparison analysis requires an Evaluation 6 details path.")
        add_arg(command, "--evaluation6-details", details)
        required_inputs = [details]
        description = f"{days}日条件の評価6手法比較詳細CSVを、三分位と固定回数帯の両方で後段集計します。"
        mode_output_dirs = [output_dir / "tertile", output_dir / "fixed"] if frequency_band_mode == "both" else [output_dir]
        expected_outputs = []
        for mode_output_dir in mode_output_dirs:
            expected_outputs.extend(
                [
                    mode_output_dir / "evaluation8_frequency_band_details.csv",
                    mode_output_dir / "evaluation8_by_frequency_band.csv",
                    mode_output_dir / "evaluation8_by_frequency_band_by_method.csv",
                    mode_output_dir / "evaluation8_occurrence_weighted_summary.csv",
                    mode_output_dir / "evaluation8_summary.json",
                ]
            )
    else:
        patterns = as_path(settings["patterns_proposed"])
        state_series = as_path(settings["state_series"])
        labeled_casas = as_path(settings.get("labeled_casas"))
        adl_intervals = as_path(settings.get("adl_intervals"))
        if patterns is None or state_series is None:
            raise ValueError("154-day proposed-only evaluation requires patterns-proposed and state-series.")
        add_arg(command, "--patterns-proposed", patterns)
        add_arg(command, "--patterns-proposed-template", settings.get("patterns_proposed_template"))
        add_arg(command, "--runs", settings["runs"])
        add_arg(command, "--state-series", state_series)
        add_arg(command, "--labeled-casas", labeled_casas)
        add_arg(command, "--adl-intervals", adl_intervals)
        add_arg(command, "--min-overlap-ratio-for-true-label", settings["min_overlap_ratio_for_true_label"])
        add_arg(command, "--no-overlap-label", settings["no_overlap_label"])
        add_arg(command, "--missing-pred-label", settings["missing_pred_label"])
        add_arg(command, "--unknown-pred-label", settings["unknown_pred_label"])
        add_arg(command, "--wake-window-minutes", settings["wake_window_minutes"])
        add_arg(command, "--match-mode", settings["match_mode"])
        add_arg(command, "--max-skip-duration-minutes", settings["max_skip_duration_minutes"])
        if frequency_band_mode in {"fixed", "both"} and settings.get("write_distribution_plots", True):
            add_flag(command, "--write-distribution-plots", True)
        elif frequency_band_mode in {"fixed", "both"}:
            add_flag(command, "--no-write-distribution-plots", True)
        run_paths = [
            proposed_run_path(
                patterns,
                settings.get("patterns_proposed_template"),
                settings.get("dataset", "aruba"),
                n_states,
                hamming,
                days,
                run,
            )
            for run in range(1, int(settings["runs"]) + 1)
        ]
        required_inputs = [*run_paths, state_series, *([labeled_casas or adl_intervals] if labeled_casas or adl_intervals else [])]
        description = (
            f"154日条件の提案手法JSONを{int(settings['runs'])} runで評価6と同じset一致処理へ通し、"
            "三分位と固定回数帯の両方を一度に集計します。"
        )
        mode_output_dirs = [output_dir / "tertile", output_dir / "fixed"] if frequency_band_mode == "both" else [output_dir]
        expected_outputs = []
        for mode_output_dir in mode_output_dirs:
            expected_outputs.extend(
                [
                    mode_output_dir / "evaluation8_frequency_band_details.csv",
                    mode_output_dir / "evaluation8_by_frequency_band.csv",
                    mode_output_dir / "evaluation8_occurrence_weighted_summary.csv",
                    mode_output_dir / "evaluation8_summary.json",
                ]
            )
        if frequency_band_mode in {"fixed", "both"} and settings.get("write_distribution_plots", True):
            fixed_output_dir = output_dir / "fixed" if frequency_band_mode == "both" else output_dir
            expected_outputs.extend(
                [
                    fixed_output_dir / "evaluation8_frequency_distribution.png",
                    fixed_output_dir / "evaluation8_frequency_band_metrics.png",
                ]
            )

    return [
        EvaluationStep(
            "eval8_frequency_stratified",
            "評価8を実行",
            description,
            command,
            required_inputs,
            expected_outputs,
        )
    ]


def build_evaluation7_steps(settings: dict[str, Any]) -> list[EvaluationStep]:
    runner = settings["runner"]
    dataset = settings["dataset"]
    days = settings["days"]
    runs = settings["runs"]
    staged_search = settings.get("staged_search", False)
    top_n = int(settings.get("top_n", 10))
    total_runs = int(settings.get("total_runs", settings.get("repeat_runs", 3)))
    patterns_template = None if staged_search else settings.get("patterns_template")
    n_states_list = settings["n_states_list"]
    hamming_thresholds = settings["hamming_thresholds"]
    labeled = as_path(settings["labeled_casas"])
    sensor_map = as_path(settings["sensor_map"])
    adl_intervals = as_path(settings["adl_intervals"])
    output_dir = as_path(settings["output_dir"])
    if output_dir is None:
        raise ValueError("Evaluation 7 output_dir is required")

    screening_summary = output_dir / "evaluation7_condition_summary.csv"
    screening_complete = staged_search and screening_summary.exists()

    def build_eval_command(
        *,
        destination: Path,
        condition_file: Path | None = None,
        run_ids: list[int] | None = None,
        run_count: int | None = None,
        strict_inputs: bool = False,
        condition_summary_copy: Path | None = None,
    ) -> list[str]:
        command = script_cmd(runner, "scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py")
        if condition_file is not None:
            add_arg(command, "--conditions-file", condition_file)
        else:
            add_multi_arg(command, "--n-states-list", n_states_list)
            add_multi_arg(command, "--hamming-thresholds", hamming_thresholds)
        add_arg(command, "--days", days)
        if run_ids is not None:
            add_multi_arg(command, "--run-ids", run_ids)
        else:
            add_arg(command, "--runs", run_count if run_count is not None else runs)
        add_arg(command, "--dataset", dataset)
        add_arg(command, "--condition-summary-copy", condition_summary_copy)
        add_arg(command, "--patterns-template", patterns_template)
        add_arg(command, "--state-series-template", settings.get("state_series_template"))
        add_arg(command, "--adl-intervals", adl_intervals)
        add_arg(command, "--labeled-casas", labeled)
        add_arg(command, "--output-dir", destination)
        add_arg(command, "--min-overlap-ratio-for-true-label", settings["min_overlap_ratio_for_true_label"])
        add_arg(command, "--no-overlap-label", settings["no_overlap_label"])
        add_arg(command, "--missing-pred-label", settings["missing_pred_label"])
        add_arg(command, "--unknown-pred-label", settings["unknown_pred_label"])
        add_arg(command, "--wake-window-minutes", settings["wake_window_minutes"])
        add_arg(command, "--match-mode", settings["match_mode"])
        add_arg(command, "--max-skip-duration-minutes", settings["max_skip_duration_minutes"])
        add_arg(command, "--selection-metric", settings["selection_metric"])
        if not strict_inputs:
            add_flag(command, "--skip-missing-runs", settings["skip_missing_runs"])
            add_flag(command, "--skip-missing-conditions", settings["skip_missing_conditions"])
        return command

    def grid_required_inputs(run_ids: list[int]) -> list[Path]:
        required: list[Path] = []
        if labeled is not None:
            required.append(labeled)
        elif adl_intervals is not None:
            required.append(adl_intervals)
        for n_states in n_states_list:
            for hamming in hamming_thresholds:
                if settings.get("state_series_template"):
                    required.append(
                        template_path(settings["state_series_template"], dataset, n_states, hamming, days)
                    )
                else:
                    required.append(default_eval_state_series_path(n_states, hamming, days))
                for run_id in run_ids:
                    if patterns_template:
                        required.append(
                            template_path(
                                patterns_template,
                                dataset,
                                n_states,
                                hamming,
                                days,
                                run=run_id,
                            )
                        )
                    else:
                        required.append(default_proposed_path(dataset, n_states, hamming, days, run=run_id))
        return required

    def evaluation_outputs(destination: Path) -> list[Path]:
        return [
            destination / "evaluation7_condition_summary.csv",
            destination / "evaluation7_condition_summary_by_run.csv",
            destination / "evaluation7_pattern_set_details.csv",
            destination / "evaluation7_by_pred_label.csv",
            destination / "evaluation7_by_true_label.csv",
            destination / "evaluation7_by_time_band.csv",
            destination / "evaluation7_summary.json",
        ]

    steps: list[EvaluationStep] = []
    if settings.get("show_preparation_steps", True) and not screening_complete:
        for n_states in n_states_list:
            for hamming in hamming_thresholds:
                cond_id = short_suffix(n_states, hamming, days)
                state_table = default_state_table(dataset, n_states, hamming, days)
                transition_json = PROJECT_ROOT / "picture" / condition_suffix(dataset, n_states, hamming, days) / "state_transition_all.json"
                state_series = (
                    template_path(settings["state_series_template"], dataset, n_states, hamming, days)
                    if settings.get("state_series_template")
                    else default_eval_state_series_path(n_states, hamming, days)
                )
                intermediate_dir = state_series.parent
                first_pattern = (
                    template_path(patterns_template, dataset, n_states, hamming, days, run=1)
                    if patterns_template
                    else default_proposed_path(dataset, n_states, hamming, days, run=1)
                )
                build_cmd = script_cmd(runner, "scripts/run_build_network_from_labeled_casas.py")
                add_arg(build_cmd, "--labeled-casas", labeled)
                add_arg(build_cmd, "--sensor-map", sensor_map)
                add_arg(build_cmd, "--days", days)
                add_arg(build_cmd, "--n-states", n_states)
                add_arg(build_cmd, "--hamming-threshold", hamming)
                add_arg(
                    build_cmd,
                    "--smoothing-window-sec",
                    settings.get("smoothing_window_sec", SMOOTHING_WINDOW_SEC),
                )
                steps.append(
                    EvaluationStep(
                        f"eval7_{cond_id}_build_network",
                        f"{cond_id}: 1. 代表状態・状態遷移ネットワークを作成",
                        "評価7のこの条件に必要な state table と状態遷移JSONを作成します。",
                        build_cmd,
                        [p for p in [labeled, sensor_map] if p is not None],
                        [state_table, transition_json],
                    )
                )

                llm_cmd = script_cmd(runner, "scripts/run_llm_extraction.py")
                add_arg(llm_cmd, "--days", days)
                add_arg(llm_cmd, "--n-states", n_states)
                add_arg(llm_cmd, "--hamming-threshold", hamming)
                add_arg(llm_cmd, "--runs", 1 if staged_search else runs)
                expected_patterns = [first_pattern]
                if not staged_search and runs > 1:
                    expected_patterns.append(
                        template_path(patterns_template, dataset, n_states, hamming, days, run=runs)
                        if patterns_template
                        else default_proposed_path(dataset, n_states, hamming, days, run=runs)
                    )
                steps.append(
                    EvaluationStep(
                        f"eval7_{cond_id}_llm",
                        f"{cond_id}: 2. 提案手法LLM出力を生成",
                        "評価7のこの条件に必要な提案手法JSONを生成します。APIキーを使う重い処理です。",
                        llm_cmd,
                        [transition_json],
                        expected_patterns,
                    )
                )

                state_series_cmd = script_cmd(runner, "scripts/evaluate_adl_labels.py")
                add_arg(state_series_cmd, "--labeled-casas", labeled)
                add_arg(state_series_cmd, "--state-table", state_table)
                add_arg(state_series_cmd, "--sensor-map", sensor_map)
                add_arg(state_series_cmd, "--patterns", first_pattern)
                add_arg(state_series_cmd, "--output-dir", intermediate_dir)
                add_arg(state_series_cmd, "--write-state-series", state_series)
                add_arg(state_series_cmd, "--hamming-threshold", hamming)
                steps.append(
                    EvaluationStep(
                        f"eval7_{cond_id}_state_series",
                        f"{cond_id}: 3. 評価7用 state_series を作成",
                        "評価7のこの条件に必要な代表状態系列CSVを作成します。",
                        state_series_cmd,
                        [p for p in [labeled, state_table, sensor_map, first_pattern] if p is not None],
                        [state_series, intermediate_dir / "pattern_occurrences.csv"],
                    )
                )

    if not staged_search:
        steps.append(
            EvaluationStep(
                "eval7_evaluate",
                "4. 評価7を実行",
                "提案手法のみを対象に、Kとハミング距離の全条件でADL解釈ラベルset一致を比較します。",
                build_eval_command(destination=output_dir, run_count=runs),
                grid_required_inputs(list(range(1, runs + 1))),
                evaluation_outputs(output_dir),
            )
        )
        return steps

    if not screening_complete:
        steps.append(
            EvaluationStep(
                "eval7_screening",
                "4. 全条件を1回評価して上位候補を決める",
                "全条件のrun 1を評価します。summaryが既にあれば一括実行ではスキップされます。",
                build_eval_command(destination=output_dir, run_count=1),
                grid_required_inputs([1]),
                [screening_summary],
            )
        )

    manifest = output_dir / f"evaluation7_top{top_n}_{total_runs}runs_conditions.csv"
    evaluation_run_ids = list(range(1, total_runs + 1))
    repeat_cmd = script_cmd(runner, "scripts/run_evaluation7_top_condition_repeats.py")
    add_arg(repeat_cmd, "--screening-summary", screening_summary)
    add_arg(repeat_cmd, "--manifest", manifest)
    add_arg(repeat_cmd, "--top-n", top_n)
    add_arg(repeat_cmd, "--total-runs", total_runs)
    add_arg(repeat_cmd, "--days", days)
    add_arg(repeat_cmd, "--dataset", dataset)
    repeat_expected_outputs = [manifest]
    if screening_summary.exists():
        try:
            selected_rows = select_top_condition_rows(screening_summary, top_n)
        except (OSError, ValueError):
            selected_rows = []
        repeat_expected_outputs.extend(
            default_proposed_path(
                dataset,
                int(row["n_states"]),
                int(row["hamming_threshold"]),
                days,
                run=run_id,
            )
            for row in selected_rows
            for run_id in range(2, total_runs + 1)
        )
    steps.append(
        EvaluationStep(
            "eval7_top_repeats",
            f"5. 上位{top_n}条件を合計{total_runs}回まで実行",
            f"既存のrun 1を再利用し、上位条件についてrun 2〜{total_runs}だけを追加生成します。",
            repeat_cmd,
            [screening_summary],
            repeat_expected_outputs,
        )
    )

    final_output_dir = output_dir / f"top{top_n}_{total_runs}runs"
    final_required_inputs = [manifest]
    if labeled is not None:
        final_required_inputs.append(labeled)
    elif adl_intervals is not None:
        final_required_inputs.append(adl_intervals)
    steps.append(
        EvaluationStep(
            "eval7_evaluate",
            f"6. 上位{top_n}条件の{total_runs}回平均で最適条件を選ぶ",
            f"初回スクリーニングrun 1を含むrun 1〜{total_runs}の平均を比較します。",
            build_eval_command(
                destination=final_output_dir,
                condition_file=manifest,
                run_ids=evaluation_run_ids,
                strict_inputs=True,
                condition_summary_copy=manifest,
            ),
            final_required_inputs,
            evaluation_outputs(final_output_dir),
        )
    )
    return steps
