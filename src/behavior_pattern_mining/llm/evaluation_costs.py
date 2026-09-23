"""Read-only full-rerun request planning for Evaluations 5--10."""

from __future__ import annotations

from contextlib import redirect_stdout
import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Sequence

from experiment_config import DATASET_NAME, ROOT_DIR
from src.behavior_pattern_mining.evaluation.evaluation7_staged import (
    condition_pairs_from_file,
)
from src.behavior_pattern_mining.llm import direct_log_extractor, pattern_extractor
from src.behavior_pattern_mining.llm.client import LLMRuntimeConfig
from src.behavior_pattern_mining.llm.cost_estimator import (
    BedrockTokenEstimate,
    estimate_bedrock_tokens,
)
from src.behavior_pattern_mining.llm.pricing import (
    CostEstimate,
    ModelPricing,
    PricingNotConfiguredError,
    build_cost_estimate,
    load_model_pricing,
)
from src.behavior_pattern_mining.visualization import state_transition_visualizer as stv


DEFAULT_EVALUATIONS = (5, 6, 7, 8, 9, 10)
EVALUATION7_N_STATES = (10, 15, 20, 25, 30, 35, 40)
EVALUATION7_HAMMING = (0, 1, 2, 3)
EVALUATION7_DAYS = 30


@dataclass(frozen=True)
class EvaluationRequestPlan:
    evaluation: int
    scope: str
    user_messages: tuple[str, ...]
    run_plan: str
    source_paths: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def request_count(self) -> int:
        return len(self.user_messages)


@dataclass(frozen=True)
class EvaluationEstimateRow:
    model_id: str
    evaluation: str
    scope: str
    requests: int
    input_tokens: int
    input_token_method: str
    input_tokens_exact: bool
    estimated_output_tokens_per_request: int | None
    estimated_output_tokens: int | None
    max_output_tokens_per_request: int | None
    max_output_tokens: int
    input_cost_usd: Decimal | None
    estimated_output_cost_usd: Decimal | None
    estimated_total_cost_usd: Decimal | None
    max_output_cost_usd: Decimal | None
    max_cost_usd: Decimal | None
    pricing_available: bool
    pricing_error: str | None
    run_plan: str
    notes: str
    input_token_warning: str | None = None


@dataclass(frozen=True)
class EvaluationCostReport:
    generated_at: str
    llm_config: LLMRuntimeConfig
    rows: tuple[EvaluationEstimateRow, ...]
    total: EvaluationEstimateRow
    plans: tuple[EvaluationRequestPlan, ...]
    pricing: ModelPricing | None
    pricing_error: str | None


CSV_FIELDS = (
    "model_id",
    "evaluation",
    "scope",
    "requests",
    "input_tokens",
    "input_token_method",
    "input_tokens_exact",
    "estimated_output_tokens_per_request",
    "estimated_output_tokens",
    "max_output_tokens_per_request",
    "max_output_tokens",
    "input_cost_usd",
    "estimated_output_cost_usd",
    "estimated_total_cost_usd",
    "max_output_cost_usd",
    "max_cost_usd",
    "pricing_available",
    "pricing_error",
    "run_plan",
    "notes",
    "input_token_warning",
)

MODEL_COMPARISON_FIELDS = (
    "model_id",
    "requests",
    "input_tokens",
    "input_token_method",
    "estimated_output_tokens",
    "max_output_tokens",
    "estimated_total_cost_usd",
    "max_cost_usd",
    "pricing_available",
    "pricing_error",
)


def _mode_messages(
    input_modes_dir: Path,
    repetitions: int,
    *,
    prompt_template: str | None = None,
) -> tuple[str, ...]:
    mode_files = pattern_extractor.find_mode_json_files(input_modes_dir)
    if prompt_template is None:
        messages = tuple(
            pattern_extractor.build_mode_user_message(path) for path in mode_files
        )
    else:
        messages = tuple(
            pattern_extractor.build_user_message(
                prompt_template,
                path.read_text(encoding="utf-8"),
                pattern_extractor.mode_label_from_path(path),
            )
            for path in mode_files
        )
    return messages * repetitions


def build_direct_log_message(
    *,
    log_days: int,
    state_days: int,
    n_states: int,
    hamming_threshold: int,
) -> str:
    """Build the same first-attempt direct-log prompt without calling an LLM."""
    csv_path, input_tmpdir, _ = direct_log_extractor.prepare_input_csv(
        direct_log_extractor.INPUT_LOG_PATH
    )
    try:
        # The visualizer is intentionally verbose during normal interactive use;
        # the batch estimator prints one consolidated table instead.
        with redirect_stdout(io.StringIO()):
            visualizer = stv.StateTransitionVisualizer(
                n_representative_states=n_states,
                hamming_threshold=hamming_threshold,
                data_duration_days=log_days,
            )
            events_df = visualizer.load_data(str(csv_path))
            state_vectors_df = visualizer.create_state_vectors(events_df)
        state_file = direct_log_extractor.find_state_file(
            DATASET_NAME,
            n_states,
            hamming_threshold,
            state_days,
        )
        _, vector_to_label = direct_log_extractor.load_state_definition(state_file)
        state_labels, _ = direct_log_extractor.map_vectors_to_states(
            state_vectors_df,
            vector_to_label,
        )
        lines = [
            f"{timestamp}\t{state_label}"
            for timestamp, state_label in zip(visualizer.state_vectors_df.index, state_labels)
        ]
        truncated = False
        if direct_log_extractor.MAX_ROWS > 0 and len(lines) > direct_log_extractor.MAX_ROWS:
            lines = lines[: direct_log_extractor.MAX_ROWS]
            truncated = True
        return (
            direct_log_extractor.build_prompt(
                dataset_name=DATASET_NAME,
                days=log_days,
                log_text="\n".join(lines),
                truncated=truncated,
            )
            .replace("{N_STATES}", str(n_states))
            .replace(
                "{STATE_TABLE}",
                direct_log_extractor.state_table_to_text(state_file),
            )
        )
    finally:
        if input_tmpdir is not None:
            input_tmpdir.cleanup()


def _evaluation5_plan(root: Path) -> EvaluationRequestPlan:
    input_dir = root / "picture" / f"{DATASET_NAME}_15_0_154days"
    return EvaluationRequestPlan(
        evaluation=5,
        scope="154-day proposed method",
        user_messages=_mode_messages(input_dir, repetitions=5),
        run_plan="K=15, h=0, days=154, runs=1-5",
        source_paths=(str(input_dir),),
    )


def _evaluation6_plan(
    root: Path,
    direct_message_builder: Callable[..., str],
) -> EvaluationRequestPlan:
    input_dir = root / "picture" / f"{DATASET_NAME}_15_0_14days"
    proposed = _mode_messages(input_dir, repetitions=5)
    direct = direct_message_builder(
        log_days=14,
        state_days=14,
        n_states=15,
        hamming_threshold=0,
    )
    return EvaluationRequestPlan(
        evaluation=6,
        scope="14-day proposed + direct-log baseline",
        user_messages=(*proposed, *((direct,) * 5)),
        run_plan="proposed K=15/h=0/days=14 runs=1-5; direct-log runs=1-5",
        source_paths=(
            str(input_dir),
            str(root / "new_labeled_data" / f"{DATASET_NAME}.txt"),
            str(root / "state" / f"{DATASET_NAME}_15_0_14days.txt"),
        ),
    )


def _evaluation7_plan(root: Path, top_conditions: Path) -> EvaluationRequestPlan:
    messages: list[str] = []
    source_paths: list[str] = [str(top_conditions)]
    for n_states in EVALUATION7_N_STATES:
        for hamming in EVALUATION7_HAMMING:
            input_dir = root / "picture" / (
                f"{DATASET_NAME}_{n_states}_{hamming}_{EVALUATION7_DAYS}days"
            )
            messages.extend(_mode_messages(input_dir, repetitions=1))
            source_paths.append(str(input_dir))

    selected = condition_pairs_from_file(
        top_conditions,
        expected_days=EVALUATION7_DAYS,
    )
    if len(selected) != 10:
        raise ValueError(
            f"Evaluation 7 repeat manifest must contain exactly 10 conditions: {top_conditions}"
        )
    screening_pairs = {
        (n_states, hamming)
        for n_states in EVALUATION7_N_STATES
        for hamming in EVALUATION7_HAMMING
    }
    unknown = [pair for pair in selected if pair not in screening_pairs]
    if unknown:
        raise ValueError(f"Evaluation 7 manifest contains non-screening conditions: {unknown}")
    for n_states, hamming in selected:
        input_dir = root / "picture" / (
            f"{DATASET_NAME}_{n_states}_{hamming}_{EVALUATION7_DAYS}days"
        )
        messages.extend(_mode_messages(input_dir, repetitions=4))

    return EvaluationRequestPlan(
        evaluation=7,
        scope="28-condition screening + selected top-10 repeats",
        user_messages=tuple(messages),
        run_plan="28 conditions run 1; manifest top 10 conditions runs 2-5",
        source_paths=tuple(dict.fromkeys(source_paths)),
        notes=(
            "Repeat prompts use the supplied top-10 manifest; a new Bedrock screening may select different conditions.",
        ),
    )


def _evaluation8_plan() -> EvaluationRequestPlan:
    return EvaluationRequestPlan(
        evaluation=8,
        scope="downstream analysis (shared Evaluations 5/6 LLM artifacts)",
        user_messages=(),
        run_plan="no additional LLM runs",
        source_paths=(),
        notes=(
            "Evaluation 8 reuses Evaluation 5's 154-day outputs and Evaluation 6's 14-day outputs; no duplicate charge is assigned.",
        ),
    )


def _expected_hestia_run_dirs(experiment: Path) -> list[Path]:
    manifest_path = experiment / "experiment.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Prepared Evaluation 9 experiment is missing experiment.json: {experiment}. "
            "Run Hestia generate and prepare before estimating."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    conditions = manifest.get("conditions")
    seeds = manifest.get("seeds")
    if not isinstance(conditions, list) or not isinstance(seeds, list):
        raise ValueError(f"Invalid Hestia experiment manifest: {manifest_path}")
    run_dirs = [
        experiment / "runs" / str(condition["id"]) / f"seed_{int(seed)}"
        for condition in conditions
        for seed in seeds
    ]
    return run_dirs


def _hestia_experiment_requests(
    experiment: Path,
    *,
    label: str,
) -> tuple[list[str], list[str], list[str]]:
    messages: list[str] = []
    source_paths: list[str] = [str(experiment / "experiment.json")]
    run_descriptions: list[str] = []
    for run_dir in _expected_hestia_run_dirs(experiment):
        run_path = run_dir / "run.json"
        network_dir = run_dir / "analysis" / "networks"
        prompt_path = run_dir / "analysis" / "prompt.md"
        if not run_path.is_file():
            raise FileNotFoundError(
                f"Prepared Evaluation 9 run is missing: {run_path}. Run Hestia prepare first."
            )
        if not prompt_path.is_file():
            raise FileNotFoundError(
                f"Prepared Evaluation 9 prompt snapshot is missing: {prompt_path}"
            )
        run_payload = json.loads(run_path.read_text(encoding="utf-8"))
        plan = run_payload.get("plan")
        if not isinstance(plan, dict):
            raise ValueError(f"Invalid Hestia run plan: {run_path}")
        repetitions = int(plan["llm_runs"])
        messages.extend(
            _mode_messages(
                network_dir,
                repetitions=repetitions,
                prompt_template=prompt_path.read_text(encoding="utf-8"),
            )
        )
        source_paths.extend((str(run_path), str(network_dir), str(prompt_path)))
        run_descriptions.append(
            f"{label}:{run_dir.parent.name}/{run_dir.name} x{repetitions}"
        )
    return messages, source_paths, run_descriptions


def _duration_window_experiments(duration_experiment: Path) -> list[tuple[int, Path]]:
    manifest_path = duration_experiment / "duration.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "Prepared Evaluation 9 duration experiment is missing duration.json: "
            f"{duration_experiment}. Run evaluate_9_duration.py --stage generate "
            "and --stage prepare before estimating."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    train_days = manifest.get("train_days") if isinstance(manifest, dict) else None
    if (
        not isinstance(train_days, list)
        or not train_days
        or any(not isinstance(days, int) or days <= 0 for days in train_days)
        or len(set(train_days)) != len(train_days)
    ):
        raise ValueError(f"Invalid Evaluation 9 duration manifest: {manifest_path}")
    return [
        (days, duration_experiment / "windows" / f"train_{days}d")
        for days in train_days
    ]


def _evaluation9_plan(
    experiment: Path,
    duration_experiment: Path,
) -> EvaluationRequestPlan:
    messages, source_paths, run_descriptions = _hestia_experiment_requests(
        experiment,
        label="standard",
    )
    duration_manifest = duration_experiment / "duration.json"
    source_paths.append(str(duration_manifest))
    duration_windows = _duration_window_experiments(duration_experiment)
    for train_days, window_experiment in duration_windows:
        window_messages, window_sources, window_descriptions = (
            _hestia_experiment_requests(
                window_experiment,
                label=f"duration-{train_days}d",
            )
        )
        messages.extend(window_messages)
        source_paths.extend(window_sources)
        run_descriptions.extend(window_descriptions)
    return EvaluationRequestPlan(
        evaluation=9,
        scope="prepared Hestia standard + train-duration experiments",
        user_messages=tuple(messages),
        run_plan=(
            f"standard plus {len(duration_windows)} duration windows; "
            f"{len(run_descriptions)} analysis runs; per-run llm_runs from run.json"
        ),
        source_paths=tuple(dict.fromkeys(source_paths)),
        notes=(
            f"Standard experiment: {experiment}",
            f"Duration experiment: {duration_experiment}",
        ),
    )


def _evaluation10_plan(output_dir: Path) -> EvaluationRequestPlan:
    preparation_path = output_dir / "preparation.json"
    network_dir = output_dir / "network"
    if not preparation_path.is_file():
        raise FileNotFoundError(
            f"Prepared Evaluation 10 input is missing: {preparation_path}. "
            "Run evaluate_10_switchbot.py --stage prepare before estimating."
        )
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    split = preparation.get("split")
    parameters = preparation.get("parameters")
    if not isinstance(split, dict) or not isinstance(parameters, dict):
        raise ValueError(f"Invalid Evaluation 10 preparation: {preparation_path}")
    return EvaluationRequestPlan(
        evaluation=10,
        scope="prepared SwitchBot holdout",
        user_messages=_mode_messages(network_dir, repetitions=1),
        run_plan=(
            f"K={parameters.get('n_states')}, h={parameters.get('hamming_threshold')}, "
            f"train_days={split.get('train_days')}, run=1"
        ),
        source_paths=(str(preparation_path), str(network_dir)),
    )


def build_evaluation_plans(
    *,
    root: Path = ROOT_DIR,
    evaluations: Sequence[int] = DEFAULT_EVALUATIONS,
    evaluation7_top_conditions: Path | None = None,
    evaluation9_experiment: Path | None = None,
    evaluation9_duration_experiment: Path | None = None,
    evaluation10_output_dir: Path | None = None,
    direct_message_builder: Callable[..., str] = build_direct_log_message,
) -> tuple[EvaluationRequestPlan, ...]:
    """Build exact first-attempt prompts without consulting LLM checkpoints."""
    selected = tuple(evaluations)
    if not selected or any(value not in DEFAULT_EVALUATIONS for value in selected):
        raise ValueError("evaluations must be selected from 5, 6, 7, 8, 9, 10")
    if len(set(selected)) != len(selected):
        raise ValueError("evaluation IDs must be unique")
    eval7_manifest = evaluation7_top_conditions or (
        root / "results/7_param_search/evaluation7_top10_5runs_conditions.csv"
    )
    hestia_experiment = evaluation9_experiment or root / "output/9_hestia/full"
    hestia_duration_experiment = evaluation9_duration_experiment or (
        root / "output/9_hestia/duration"
    )
    switchbot_output = evaluation10_output_dir or (
        root / "output/10_switchbot/2026-09-01_2026-09-08"
    )
    builders = {
        5: lambda: _evaluation5_plan(root),
        6: lambda: _evaluation6_plan(root, direct_message_builder),
        7: lambda: _evaluation7_plan(root, eval7_manifest),
        8: _evaluation8_plan,
        9: lambda: _evaluation9_plan(
            hestia_experiment,
            hestia_duration_experiment,
        ),
        10: lambda: _evaluation10_plan(switchbot_output),
    }
    return tuple(builders[evaluation]() for evaluation in selected)


def _row_from_estimate(
    *,
    plan: EvaluationRequestPlan,
    llm_config: LLMRuntimeConfig,
    token_estimate: BedrockTokenEstimate,
    cost_estimate: CostEstimate | None,
    pricing_error: str | None,
) -> EvaluationEstimateRow:
    return EvaluationEstimateRow(
        model_id=llm_config.model_name,
        evaluation=str(plan.evaluation),
        scope=plan.scope,
        requests=token_estimate.request_count,
        input_tokens=token_estimate.input_tokens,
        input_token_method=token_estimate.input_token_method,
        input_tokens_exact=token_estimate.input_tokens_exact,
        estimated_output_tokens_per_request=(
            token_estimate.estimated_output_tokens_per_request
        ),
        estimated_output_tokens=token_estimate.estimated_output_tokens,
        max_output_tokens_per_request=token_estimate.max_output_tokens_per_request,
        max_output_tokens=token_estimate.max_output_tokens,
        input_cost_usd=(None if cost_estimate is None else cost_estimate.input_cost_usd),
        estimated_output_cost_usd=(
            None if cost_estimate is None else cost_estimate.estimated_output_cost_usd
        ),
        estimated_total_cost_usd=(
            None if cost_estimate is None else cost_estimate.estimated_total_cost_usd
        ),
        max_output_cost_usd=(
            None if cost_estimate is None else cost_estimate.max_output_cost_usd
        ),
        max_cost_usd=(
            None if cost_estimate is None else cost_estimate.max_cost_estimate_usd
        ),
        pricing_available=cost_estimate is not None,
        pricing_error=pricing_error,
        run_plan=plan.run_plan,
        notes=" ".join(plan.notes),
        input_token_warning=token_estimate.input_token_warning,
    )


def estimate_evaluation_plans(
    *,
    llm_config: LLMRuntimeConfig,
    plans: Sequence[EvaluationRequestPlan],
) -> EvaluationCostReport:
    """Estimate every evaluation and a sum row; never invoke model inference."""
    try:
        pricing = load_model_pricing(llm_config.model_name)
        pricing_error = None
    except PricingNotConfiguredError as exc:
        pricing = None
        pricing_error = str(exc)

    token_estimates = [
        estimate_bedrock_tokens(
            llm_config=llm_config,
            user_messages=plan.user_messages,
            skipped_count=0,
        )
        for plan in plans
    ]
    cost_estimates: list[CostEstimate | None] = []
    for token_estimate in token_estimates:
        if pricing is None:
            cost_estimates.append(None)
            continue
        cost_estimates.append(
            build_cost_estimate(
                model_id=llm_config.model_name,
                request_count=token_estimate.request_count,
                skipped_count=token_estimate.skipped_count,
                input_tokens=token_estimate.input_tokens,
                input_tokens_exact=token_estimate.input_tokens_exact,
                input_token_method=token_estimate.input_token_method,
                input_token_warning=token_estimate.input_token_warning,
                estimated_output_tokens_per_request=(
                    token_estimate.estimated_output_tokens_per_request
                ),
                max_output_tokens_per_request=(
                    token_estimate.max_output_tokens_per_request
                ),
            )
        )
    rows = tuple(
        _row_from_estimate(
            plan=plan,
            llm_config=llm_config,
            token_estimate=token_estimate,
            cost_estimate=cost_estimate,
            pricing_error=pricing_error,
        )
        for plan, token_estimate, cost_estimate in zip(
            plans,
            token_estimates,
            cost_estimates,
        )
    )
    all_exact = all(row.input_tokens_exact for row in rows)
    methods = tuple(
        dict.fromkeys(row.input_token_method for row in rows if row.requests > 0)
    ) or ("No requests",)
    warnings = [row.input_token_warning for row in rows if row.input_token_warning]
    total_token_estimate = BedrockTokenEstimate(
        request_count=sum(row.requests for row in rows),
        skipped_count=0,
        input_tokens=sum(row.input_tokens for row in rows),
        input_tokens_exact=all_exact,
        input_token_method="; ".join(methods),
        input_token_warning=" | ".join(warnings) or None,
        estimated_output_tokens_per_request=llm_config.estimated_output_tokens,
        estimated_output_tokens=(
            None
            if llm_config.estimated_output_tokens is None
            else sum(row.estimated_output_tokens or 0 for row in rows)
        ),
        max_output_tokens_per_request=llm_config.max_tokens or 0,
        max_output_tokens=sum(row.max_output_tokens for row in rows),
    )
    total_cost_estimate = None
    if pricing is not None:
        total_cost_estimate = build_cost_estimate(
            model_id=llm_config.model_name,
            request_count=total_token_estimate.request_count,
            skipped_count=0,
            input_tokens=total_token_estimate.input_tokens,
            input_tokens_exact=total_token_estimate.input_tokens_exact,
            input_token_method=total_token_estimate.input_token_method,
            input_token_warning=total_token_estimate.input_token_warning,
            estimated_output_tokens_per_request=(
                total_token_estimate.estimated_output_tokens_per_request
            ),
            max_output_tokens_per_request=(
                total_token_estimate.max_output_tokens_per_request
            ),
        )
    total = _row_from_estimate(
        plan=EvaluationRequestPlan(
            evaluation=0,
            scope="all selected evaluations",
            user_messages=(),
            run_plan="sum of evaluation rows",
            source_paths=(),
        ),
        llm_config=llm_config,
        token_estimate=total_token_estimate,
        cost_estimate=total_cost_estimate,
        pricing_error=pricing_error,
    )
    total = EvaluationEstimateRow(**{**asdict(total), "evaluation": "TOTAL"})
    return EvaluationCostReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        llm_config=llm_config,
        rows=rows,
        total=total,
        plans=tuple(plans),
        pricing=pricing,
        pricing_error=pricing_error,
    )


def estimate_models(
    *,
    llm_configs: Sequence[LLMRuntimeConfig],
    plans: Sequence[EvaluationRequestPlan],
) -> tuple[EvaluationCostReport, ...]:
    """Estimate each model independently, including model-specific CountTokens."""
    model_ids = [config.model_name for config in llm_configs]
    if not model_ids or any(not model_id for model_id in model_ids):
        raise ValueError("at least one non-empty Bedrock model ID is required")
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("Bedrock model IDs must be unique")
    return tuple(
        estimate_evaluation_plans(llm_config=config, plans=plans)
        for config in llm_configs
    )


def _decimal_text(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _row_dict(row: EvaluationEstimateRow) -> dict[str, object]:
    payload = asdict(row)
    for field in (
        "input_cost_usd",
        "estimated_output_cost_usd",
        "estimated_total_cost_usd",
        "max_output_cost_usd",
        "max_cost_usd",
    ):
        payload[field] = _decimal_text(getattr(row, field))
    return payload


def save_evaluation_cost_report(
    report: EvaluationCostReport,
    *,
    csv_path: Path,
    json_path: Path,
) -> None:
    """Backward-compatible single-model writer."""
    _write_detailed_csv((report,), csv_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(_comparison_json_payload((report,)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_detailed_csv(
    reports: Sequence[EvaluationCostReport],
    csv_path: Path,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for report in reports:
            for row in (*report.rows, report.total):
                writer.writerow(_row_dict(row))


def _model_json_payload(report: EvaluationCostReport) -> dict[str, object]:
    pricing_payload = None
    if report.pricing is not None:
        pricing_payload = {
            "input_usd_per_1m_tokens": _decimal_text(
                report.pricing.input_usd_per_1m_tokens
            ),
            "output_usd_per_1m_tokens": _decimal_text(
                report.pricing.output_usd_per_1m_tokens
            ),
            "note": report.pricing.note,
        }
    return {
        "model_id": report.llm_config.model_name,
        "pricing_available": report.pricing is not None,
        "pricing_error": report.pricing_error,
        "pricing": pricing_payload,
        "evaluations": [
            {
                **_row_dict(row),
                "source_paths": list(plan.source_paths),
                "count_tokens": {
                    "exact": row.input_tokens_exact,
                    "method": row.input_token_method,
                    "warning": row.input_token_warning,
                },
            }
            for row, plan in zip(report.rows, report.plans)
        ],
        "total": _row_dict(report.total),
    }


def _comparison_json_payload(
    reports: Sequence[EvaluationCostReport],
) -> dict[str, object]:
    if not reports:
        raise ValueError("at least one model report is required")
    first = reports[0]
    estimate_settings = first.rows[0] if first.rows else first.total
    payload: dict[str, object] = {
        "generated_at": first.generated_at,
        "provider": "bedrock",
        "region": first.llm_config.region_name,
        "settings": {
            "full_rerun": True,
            "checkpoint_policy": "ignored (read-only)",
            "retries_included": False,
            "bedrock_estimated_output_tokens": (
                estimate_settings.estimated_output_tokens_per_request
            ),
            "bedrock_max_tokens": estimate_settings.max_output_tokens_per_request,
            "inference_executed": False,
        },
        "models": [_model_json_payload(report) for report in reports],
    }
    # Keep the just-introduced single-model JSON fields available to existing readers.
    if len(reports) == 1:
        model_payload = _model_json_payload(first)
        payload.update(model_payload)
    return payload


def save_model_comparison_reports(
    reports: Sequence[EvaluationCostReport],
    *,
    csv_path: Path,
    json_path: Path,
    summary_csv_path: Path,
) -> None:
    """Save per-evaluation model rows, structured JSON, and TOTAL comparison."""
    if not reports:
        raise ValueError("at least one model report is required")
    _write_detailed_csv(reports, csv_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(_comparison_json_payload(reports), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODEL_COMPARISON_FIELDS)
        writer.writeheader()
        for report in reports:
            total = report.total
            writer.writerow(
                {
                    field: _row_dict(total)[field]
                    for field in MODEL_COMPARISON_FIELDS
                }
            )


def _usd(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    rounded = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f"${rounded:,.4f}"


def format_evaluation_cost_report(
    report: EvaluationCostReport,
    *,
    csv_path: Path,
    json_path: Path,
) -> str:
    rows = (*report.rows, report.total)
    lines = [
        "=== Bedrock Evaluation Cost Estimate ===",
        "",
        f"Model: {report.llm_config.model_name}",
        f"Region: {report.llm_config.region_name}",
        "Full rerun: yes (existing checkpoints ignored; source artifacts unchanged)",
        "",
        f"{'Evaluation':<12}{'Requests':>10}{'Input tokens':>16}{'Est. output':>16}{'Est. cost':>14}{'Max cost':>14}",
    ]
    for row in rows:
        estimated_output = (
            "N/A" if row.estimated_output_tokens is None else f"{row.estimated_output_tokens:,}"
        )
        lines.append(
            f"{row.evaluation:<12}{row.requests:>10,}{row.input_tokens:>16,}"
            f"{estimated_output:>16}{_usd(row.estimated_total_cost_usd):>14}"
            f"{_usd(row.max_cost_usd):>14}"
        )
    lines.extend(["", "Input token method:"])
    for row in report.rows:
        prefix = "" if row.input_tokens_exact else "approximate: "
        lines.append(f"  {row.evaluation}: {prefix}{row.input_token_method}")
    lines.extend(
        [
            "",
            "Retries are not included.",
            "No model inference was executed.",
            f"CSV: {csv_path}",
            f"JSON: {json_path}",
        ]
    )
    return "\n".join(lines)


def format_model_comparison(
    reports: Sequence[EvaluationCostReport],
    *,
    csv_path: Path,
    json_path: Path,
    summary_csv_path: Path,
) -> str:
    """Render model-specific TOTAL token and price comparisons."""
    if not reports:
        raise ValueError("at least one model report is required")
    model_width = max(12, max(len(report.llm_config.model_name) for report in reports))
    lines = [
        "=== Model Comparison ===",
        "",
        f"{'Model':<{model_width}}  {'Requests':>10}  {'Input tokens':>14}  "
        f"{'Est. total':>12}  {'Max cost':>12}",
    ]
    for report in reports:
        total = report.total
        token_prefix = "" if total.input_tokens_exact else "~"
        lines.append(
            f"{report.llm_config.model_name:<{model_width}}  {total.requests:>10,}  "
            f"{token_prefix + format(total.input_tokens, ','):>14}  "
            f"{_usd(total.estimated_total_cost_usd):>12}  "
            f"{_usd(total.max_cost_usd):>12}"
        )
        if report.pricing_error:
            lines.append(f"  Pricing unavailable: {report.pricing_error}")
    lines.extend(
        [
            "",
            "Input tokens were counted independently for each model ID.",
            "Retries are not included.",
            "No model inference was executed.",
            f"Detailed CSV: {csv_path}",
            f"JSON: {json_path}",
            f"Summary CSV: {summary_csv_path}",
        ]
    )
    return "\n".join(lines)
