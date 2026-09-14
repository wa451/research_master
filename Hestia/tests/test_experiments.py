from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from smart_home_sim.cli import app
from smart_home_sim.engine import SimulationEngine, hash_output_directory
from smart_home_sim.experiments.artifacts import (
    activity_truth,
    generate,
    read_json,
    select_runs,
    tree_hashes,
    write_json,
)
from smart_home_sim.experiments.evaluation import (
    aggregate,
    frequency_baseline,
    score_runs,
    write_summary,
)
from smart_home_sim.experiments.metrics import (
    Occurrence,
    State,
    adl_scores,
    build_gold_catalog,
    catalog_from_training,
    evaluate_payload,
    occurrences,
    parse_predictions,
    ratios,
)
from smart_home_sim.experiments.plan import (
    Condition,
    ExperimentPlan,
    TargetActivity,
    default_conditions,
)
from smart_home_sim.experiments.research import extraction_budget
from smart_home_sim.experiments.research_worker import main as research_worker_main
from smart_home_sim.experiments.scenarios import build_scenario

START = datetime.fromisoformat("2025-01-06T00:00:00+09:00")


def t(minutes: float, day: int = 0) -> datetime:
    return START + timedelta(days=day, minutes=minutes)


def episode(start: datetime, end: datetime, resident: str = "r1", label: str = "Meal") -> dict:
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "resident_id": resident,
        "activity_id": "meal",
        "label": label,
        "complete": True,
    }


def small_plan() -> ExperimentPlan:
    return ExperimentPlan(
        train_days=1,
        test_days=1,
        seeds=[42],
        llm_runs=2,
        conditions=[Condition(id="compact_two", house="compact", residents=2)],
    )


@pytest.mark.parametrize("condition", default_conditions(), ids=lambda item: item.id)
def test_every_condition_simulates_without_noise(condition: Condition, tmp_path: Path) -> None:
    plan = small_plan()
    scenario = build_scenario(condition, plan)
    assert not scenario.sensor_imperfections.enabled
    result = SimulationEngine(scenario, days=2, seed=11).run(tmp_path / condition.id)
    assert result.event_count > 0
    assert not (result.output_dir / "events_observed.csv").exists()
    with (result.output_dir / "activity_trace.csv").open(newline="") as stream:
        trace = list(csv.DictReader(stream))
    assert not [row for row in trace if row["phase"] == "SKIPPED"]


def test_matrix_is_one_factor_at_a_time() -> None:
    conditions = default_conditions()
    assert len(conditions) == 24
    for house in ("compact", "corridor", "branched"):
        base = next(item for item in conditions if item.id == f"{house}_base").model_dump()
        for item in conditions:
            if item.house == house and not item.id.endswith("_base"):
                assert (
                    sum(
                        value != base[key]
                        for key, value in item.model_dump().items()
                        if key != "id"
                    )
                    == 1
                )


@pytest.mark.parametrize(
    "update",
    [
        {"observation_noise": True},
        {"train_days": 0},
        {"seeds": [1, 1]},
        {"start_datetime": "2025-01-06T00:00:00"},
        {"start_datetime": "2025-01-06T00:00:01+09:00"},
        {"unknown_noise": 1},
    ],
)
def test_plan_rejects_invalid_settings(update: dict) -> None:
    with pytest.raises(ValidationError):
        ExperimentPlan.model_validate({**small_plan().model_dump(), **update})


def test_target_plan_validates_time_band_and_controls_routine() -> None:
    target = TargetActivity(
        id="morning_meal",
        activity_id="meal",
        resident_id="resident_1",
        time_band="Morning",
        scheduled_start_minutes=[390, 450],
    )
    plan = ExperimentPlan(
        train_days=1,
        test_days=1,
        seeds=[11],
        conditions=[Condition(id="controlled", house="compact", variability="fixed")],
        targets=[target],
    )
    scenario = build_scenario(plan.conditions[0], plan)
    routine = scenario.residents[0].weekly_routine[next(iter(scenario.residents[0].weekly_routine))]
    target_entries = [
        item for item in routine if not isinstance(item, str) and item.activity_id == "meal"
    ]
    assert [item.scheduled_start_minute for item in target_entries] == [390, 450]
    assert not [
        item
        for item in routine
        if not isinstance(item, str) and item.activity_id in {"relax", "work"}
    ]
    with pytest.raises(ValidationError, match="outside Morning"):
        TargetActivity(
            id="bad_band",
            activity_id="meal",
            resident_id="resident_1",
            time_band="Morning",
            scheduled_start_minutes=[720],
        )
    hygiene_plan = plan.model_copy(
        update={
            "targets": [
                TargetActivity(
                    id="morning_hygiene",
                    activity_id="hygiene",
                    resident_id="resident_1",
                    time_band="Morning",
                    scheduled_start_minutes=[420],
                )
            ]
        }
    )
    hygiene_scenario = build_scenario(hygiene_plan.conditions[0], hygiene_plan)
    hygiene_routine = hygiene_scenario.residents[0].weekly_routine[
        next(iter(hygiene_scenario.residents[0].weekly_routine))
    ]
    assert [
        item.scheduled_start_minute
        for item in hygiene_routine
        if not isinstance(item, str) and item.activity_id == "hygiene"
    ] == [420]


def test_controlled_target_generation_is_reproducible_and_tracks_realized_path(
    tmp_path: Path,
) -> None:
    plan = ExperimentPlan(
        train_days=1,
        test_days=1,
        seeds=[11],
        llm_runs=1,
        conditions=[Condition(id="controlled", house="compact", variability="fixed")],
        targets=[
            TargetActivity(
                id="morning_meal",
                activity_id="meal",
                resident_id="resident_1",
                time_band="Morning",
                scheduled_start_minutes=[390],
            )
        ],
    )
    first = generate(plan, tmp_path / "first")[0]
    second = generate(plan, tmp_path / "second")[0]
    assert hash_output_directory(tmp_path / "first") == hash_output_directory(tmp_path / "second")
    assert tree_hashes(first) == tree_hashes(second)
    episodes = read_json(first / "truth/target_episodes.json")
    assert len(episodes) == 2
    assert all(episode["generated"] and episode["complete"] for episode in episodes)
    assert all(episode["target_id"] == "morning_meal" for episode in episodes)
    assert all(episode["intended_repetitions_total"] == 2 for episode in episodes)
    assert all(
        [step["step_id"] for step in episode["actual_behavior_path"]]
        == ["prepare", "use", "finish"]
        for episode in episodes
    )


def test_generation_is_byte_reproducible_and_sensor_only(tmp_path: Path) -> None:
    plan = small_plan()
    first = generate(plan, tmp_path / "first")[0]
    second = generate(plan, tmp_path / "second")[0]
    assert hash_output_directory(tmp_path / "first") == hash_output_directory(tmp_path / "second")
    assert tree_hashes(first) == tree_hashes(second)
    assert generate(plan, tmp_path / "first") == [first]
    assert select_runs(tmp_path / "first", "compact_two", 42) == [first]
    lines = (first / "input/sensors.txt").read_text().splitlines()
    assert all(len(line.split()) == 4 for line in lines)
    assert not any("resident" in line or "activity" in line or "Meal" in line for line in lines)
    assert len(set(read_json(first / "input/sensor_map.json").values())) == len(
        read_json(first / "input/sensor_map.json")
    )
    target_episode = read_json(first / "truth/target_episodes.json")[0]
    assert {
        "target_id",
        "resident_id",
        "activity_id",
        "start",
        "end",
        "time_band",
        "intended_repetitions_per_day",
        "actual_behavior_path",
    } <= set(target_episode)
    assert all(
        datetime.fromisoformat(" ".join(line.split()[:2])).date() == START.date()
        for line in (first / "input/train.txt").read_text().splitlines()
    )
    (first / "input/train.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="changed or missing"):
        generate(plan, tmp_path / "first")


def test_generation_refuses_existing_or_changed_plan(tmp_path: Path) -> None:
    (tmp_path / "unrelated.txt").write_text("keep")
    with pytest.raises(ValueError, match="empty"):
        generate(small_plan(), tmp_path)
    plan = small_plan()
    generate(plan, tmp_path / "new")
    plan.test_days = 2
    with pytest.raises(ValueError, match="differs"):
        generate(plan, tmp_path / "new")
    assert (tmp_path / "unrelated.txt").read_text() == "keep"


def test_resident_aware_truth_pairs_overlapping_same_labels(tmp_path: Path) -> None:
    path = tmp_path / "events.csv"
    fields = ["device_type", "resident_id", "activity_id", "activity_label", "timestamp", "state"]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for resident, state, minute in [("a", "START", 0), ("b", "START", 1), ("a", "END", 2)]:
            writer.writerow(
                dict(
                    zip(
                        fields,
                        [
                            "ActivityBoundary",
                            resident,
                            "meal",
                            "Meal",
                            t(minute).isoformat(),
                            state,
                        ],
                        strict=True,
                    )
                )
            )
    truth = activity_truth(path, t(3))
    assert [(row["resident_id"], row["end"], row["complete"]) for row in truth] == [
        ("a", t(2).isoformat(), True),
        ("b", t(3).isoformat(timespec="microseconds"), False),
    ]


def test_sequence_matching_preserves_barriers_and_boundaries() -> None:
    series = [
        State(t(359), t(360), "A"),
        State(t(360), t(361), "B"),
        State(t(361), t(362), "Other"),
        State(t(362), t(363), "C"),
        State(t(364), t(365), "D"),
        State(t(365), t(366), "E"),
    ]
    items = occurrences(series, t(0), t(1440))
    assert [(item.mode, item.sequence) for item in items] == [("Morning", ("D", "E"))]
    assert occurrences(series, t(365), t(366)) == []
    assert (
        occurrences([State(t(1439), t(1440), "A"), State(t(1440), t(1441), "B")], t(0), t(2880))
        == []
    )


def test_truth_is_training_only_and_support_counts_episodes() -> None:
    repeated = [
        Occurrence(t(1), t(2), "Midnight", ("A", "B")),
        Occurrence(t(3), t(4), "Midnight", ("A", "B")),
        Occurrence(t(1, 1), t(2, 1), "Midnight", ("C", "D")),
    ]
    labels = [episode(t(0), t(5)), episode(t(0, 1), t(5, 1))]
    catalog, diagnostics = catalog_from_training(repeated, labels, t(1440), 2)
    assert catalog == {}
    catalog, _ = catalog_from_training(repeated, labels, t(1440), 1)
    assert set(catalog) == {("Midnight", ("A", "B"))}
    assert diagnostics["complete_target_episodes"] == 1


def test_adl_union_does_not_double_count_residents_or_predictions() -> None:
    key = ("Midnight", ("A", "B"))
    items = [Occurrence(t(0), t(10), *key), Occurrence(t(0), t(10), *key)]
    truth = [episode(t(0), t(10)), episode(t(0), t(10), resident="r2")]
    scores = adl_scores({key: {"Meal"}}, items, truth, t(0), t(20))
    assert scores["per_label"]["Meal"]["truth_seconds"] == 600
    assert scores["per_label"]["Meal"]["predicted_seconds"] == 600
    assert scores["macro_f1"] == 1
    assert scores["annotated_fraction"] == 0.5
    wrong = adl_scores({key: {"Work"}}, items, truth, t(0), t(20))
    assert wrong["macro_f1"] == 0
    simultaneous = adl_scores(
        {key: {"Meal", "Work"}}, items, [*truth, episode(t(0), t(10), "r2", "Work")], t(0), t(20)
    )
    assert simultaneous["macro_f1"] == 1


def test_prediction_parsing_handles_native_merged_outputs_and_rejects_unknown_labels() -> None:
    payload = [
        {
            "sequence": ["S1", "S2"],
            "time_band_interpretations": {"Morning": {"ADL系列ラベル": ["Meal"]}},
        }
    ]
    assert parse_predictions(payload * 2, require_labels=True) == {
        ("Morning", ("S1", "S2")): {"Meal"}
    }
    assert parse_predictions([], require_labels=True) == {}
    for labels in ([], ["Noise"], "Meal"):
        with pytest.raises(ValueError):
            parse_predictions([{"sequence": ["S1", "S2"], "labels": labels}], require_labels=True)
    assert ratios(0, 0, 0) == {"precision": None, "recall": None, "f1": None}
    assert ratios(0, 0, 1)["f1"] == 0


def synthetic_run(tmp_path: Path) -> Path:
    plan = small_plan()
    plan.min_train_support = 1
    write_json(
        tmp_path / "run.json",
        {
            "condition": plan.conditions[0].model_dump(),
            "seed": 42,
            "plan": plan.model_dump(mode="json"),
        },
    )
    write_json(
        tmp_path / "truth/activities.json", [episode(t(360), t(362)), episode(t(360, 1), t(362, 1))]
    )
    (tmp_path / "analysis").mkdir()
    with (tmp_path / "analysis/state_series.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["start_time", "end_time", "state_id"])
        for day in (0, 1):
            for minute, state in [(360, "S1"), (361, "S2")]:
                writer.writerow([t(minute, day).isoformat(), t(minute + 1, day).isoformat(), state])
    write_json(tmp_path / "generated.json", {"files": {}})
    snapshot_analysis(tmp_path)
    return tmp_path


def controlled_gold_run(tmp_path: Path) -> Path:
    plan = ExperimentPlan(
        train_days=2,
        test_days=2,
        seeds=[11],
        llm_runs=1,
        min_train_support=2,
        conditions=[Condition(id="controlled", house="compact", variability="fixed")],
        targets=[
            TargetActivity(
                id="morning_meal",
                activity_id="meal",
                resident_id="resident_1",
                time_band="Morning",
                scheduled_start_minutes=[360],
            )
        ],
    )
    write_json(
        tmp_path / "run.json",
        {
            "condition": plan.conditions[0].model_dump(),
            "seed": 11,
            "plan": plan.model_dump(mode="json"),
        },
    )
    activities = [episode(t(360, day), t(364, day)) for day in range(4)]
    write_json(tmp_path / "truth/activities.json", activities)
    write_json(
        tmp_path / "truth/target_episodes.json",
        [
            {
                **activity,
                "target_id": "morning_meal",
                "target_episode_id": f"morning_meal_day{day + 1}_1",
                "generated": True,
                "scheduled_start": t(360, day).isoformat(),
                "configured_time_band": "Morning",
                "time_band": "Morning",
                "intended_repetitions_per_day": 1,
                "intended_repetitions_total": 4,
                "selected_template_ids": ["meal_motif"],
                "actual_behavior_path": [],
            }
            for day, activity in enumerate(activities)
        ],
    )
    (tmp_path / "analysis").mkdir()
    with (tmp_path / "analysis/state_series.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["start_time", "end_time", "state_id"])
        for day in range(4):
            for minute, state in enumerate(("A", "B", "C", "D"), start=360):
                writer.writerow([t(minute, day).isoformat(), t(minute + 1, day).isoformat(), state])
    write_json(tmp_path / "generated.json", {"files": {}})
    snapshot_analysis(tmp_path)
    return tmp_path


def snapshot_analysis(run: Path) -> None:
    write_json(
        run / "prepared.json",
        {
            "files": {
                f"analysis/{name}": digest for name, digest in tree_hashes(run / "analysis").items()
            }
        },
    )


def test_exact_oracle_and_empty_outputs_are_scored_differently_from_missing(tmp_path: Path) -> None:
    run = synthetic_run(tmp_path)
    payload = [{"sequence": ["S1", "S2"], "mode": "Morning", "labels": ["Meal"]}]
    scores = evaluate_payload(run, payload, semantic=True)
    assert scores["catalog_recall"] == scores["test_target_episode_coverage"] == 1
    assert scores["adl"]["macro_f1"] == 1
    assert scores["num_potential_fragments"] == 0
    assert scores["fragmentation_rate"] is None
    assert scores["fragmentation_status"] == "not_applicable_no_potential_fragments"
    empty = evaluate_payload(run, [], semantic=True)
    assert empty["catalog_recall"] == empty["adl"]["macro_f1"] == 0
    missing = score_runs([run], "llm")
    assert [row["status"] for row in missing] == ["missing", "missing"]
    assert all(row["metrics"]["TP"] is None for row in missing)
    assert all(row["metrics"]["fragmentation_status"] == "not_evaluated" for row in missing)
    frequency_baseline(run)
    assert read_json(run / "predictions/frequency.json")[0]["sequence"] == ["S1", "S2"]
    assert score_runs([run], "frequency")[0]["metrics"]["adl"] is None


def test_controlled_pilot_exact_scores_and_gold_based_fragmentation(tmp_path: Path) -> None:
    run = controlled_gold_run(tmp_path)
    perfect = [{"sequence": ["A", "B", "C", "D"], "mode": "Morning", "labels": ["Meal"]}]
    scores = evaluate_payload(run, perfect, semantic=True)
    assert (scores["TP"], scores["FP"], scores["FN"]) == (1, 0, 0)
    assert scores["precision"] == scores["recall"] == scores["f1"] == 1
    assert scores["num_potential_fragments"] == 5
    assert scores["num_emitted_fragments"] == 0
    assert scores["fragmentation_rate"] == 0
    canonical = [row for row in scores["gold_catalog"] if row["is_canonical"]]
    assert [row["representative_state_sequence"] for row in canonical] == [["A", "B", "C", "D"]]
    assert canonical[0]["test_episode_count"] == 2

    with_fragment = evaluate_payload(
        run,
        [*perfect, {"sequence": ["A", "B"], "mode": "Morning", "labels": ["Meal"]}],
        semantic=True,
    )
    assert with_fragment["precision"] == 0.5
    assert with_fragment["recall"] == 1
    assert with_fragment["f1"] == pytest.approx(2 / 3)
    assert with_fragment["num_emitted_fragments"] == 1
    assert with_fragment["fragmentation_rate"] == pytest.approx(1 / 5)
    assert with_fragment["fragmentation_status"] == "evaluated"

    missing_gold = evaluate_payload(run, [], semantic=True)
    assert missing_gold["recall"] == 0
    assert missing_gold["f1"] == 0


def test_legitimate_canonical_subsequence_is_not_a_potential_fragment() -> None:
    projected = []
    for day in range(3):
        for target_id, sequence in (("long", ["A", "B", "C"]), ("short", ["A", "B"])):
            projected.append(
                {
                    **episode(t(360, day), t(365, day)),
                    "target_id": target_id,
                    "target_episode_id": f"{target_id}_{day}",
                    "generated": True,
                    "representative_state_sequence": sequence,
                    "representative_state_sequences": [
                        {"time_band": "Morning", "sequence": sequence}
                    ],
                }
            )
    catalog = build_gold_catalog(projected, t(0, 2), t(0, 3), min_support=2)
    canonical = {
        tuple(row["representative_state_sequence"]) for row in catalog if row["is_canonical"]
    }
    fragments = {
        tuple(row["representative_state_sequence"]) for row in catalog if not row["is_canonical"]
    }
    assert canonical == {("A", "B"), ("A", "B", "C")}
    assert fragments == {("B", "C")}


def test_baseline_does_not_read_truth_or_learn_heldout_patterns(tmp_path: Path) -> None:
    run = synthetic_run(tmp_path)
    (run / "truth/activities.json").write_text("not json")
    path = run / "analysis/state_series.csv"
    path.write_text(
        path.read_text().replace("2025-01-07T06:01:00+09:00,S2", "2025-01-07T06:01:00+09:00,S9")
    )
    snapshot_analysis(run)
    frequency_baseline(run)
    assert read_json(run / "predictions/frequency.json")[0]["sequence"] == ["S1", "S2"]


def test_aggregation_excludes_incomplete_seeds_and_does_not_pool_llm_runs(tmp_path: Path) -> None:
    scores = evaluate_payload(synthetic_run(tmp_path), [], semantic=True)
    base = {"condition": "c", "method": "llm", "status": "complete", "metrics": scores}
    rows = [
        {**base, "seed": 1, "run_id": 1},
        {**base, "seed": 1, "run_id": 2},
        {**base, "seed": 2, "run_id": 1},
        {**base, "seed": 2, "run_id": 2, "status": "missing"},
    ]
    summary = aggregate(rows)[0]
    assert summary["complete_runs"] == 3
    assert summary["complete_seeds"] == summary["catalog_recall_n_seeds"] == 1
    assert summary["catalog_recall_mean"] == 0
    assert summary["catalog_recall_std"] is None


def test_summary_writes_aggregate_and_run_status_contract(tmp_path: Path) -> None:
    metrics = evaluate_payload(controlled_gold_run(tmp_path / "run"), [], semantic=True)
    rows = [
        {
            "condition": "controlled",
            "seed": 11,
            "method": "llm",
            "run_id": 1,
            "status": "complete",
            "metrics": metrics,
        },
        {
            "condition": "controlled",
            "seed": 11,
            "method": "llm",
            "run_id": 2,
            "status": "missing",
            "reason": "fixture missing",
        },
    ]
    output = tmp_path / "results/evaluation9_summary"
    write_summary(output, rows)
    with output.with_name("evaluation9_summary_runs.csv").open(newline="") as stream:
        details = list(csv.DictReader(stream))
    assert details[0]["status"] == "complete"
    assert details[0]["TP"] == "0"
    assert details[0]["FN"] == "1"
    assert details[1]["missing"] == "1"
    with output.with_suffix(".csv").open(newline="") as stream:
        summary = next(csv.DictReader(stream))
    assert summary["complete_runs"] == "1"
    assert summary["missing_runs"] == "1"
    assert "precision_mean" in summary
    payload = read_json(output.with_suffix(".json"))
    assert {row["status"] for row in payload["runs"]} == {"complete", "missing"}


def test_extract_cli_defaults_to_no_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run = synthetic_run(tmp_path / "run")
    (run / "analysis/networks").mkdir()
    for mode in ("all", "Morning", "Night", "Midnight", "Daytime"):
        write_json(run / "analysis/networks" / f"state_transition_{mode}.json", {})
    write_json(
        run / "analysis/llm_settings.json",
        {"model": "test", "temperature": 0.2, "max_parse_retries": 3},
    )
    snapshot_analysis(run)
    budget = extraction_budget(run)
    assert budget["modes"] == 4
    assert budget["fresh_mode_calls_upper_bound"] == 8
    monkeypatch.setattr("smart_home_sim.experiments.cli.select_runs", lambda *args: [run])
    calls = []
    monkeypatch.setattr(
        "smart_home_sim.experiments.cli.extract_run", lambda *args: calls.append(args)
    )
    result = CliRunner().invoke(
        app, ["experiment", "extract", str(tmp_path), "--research-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "No API calls made" in result.output
    assert calls == []


def test_worker_extract_uses_saved_prompt_model_and_distinct_run_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run = synthetic_run(tmp_path / "run")
    write_json(run / "analysis/llm_settings.json", {"model": "saved-model", "temperature": 0.12})
    (run / "analysis/prompt.md").write_text("saved prompt", encoding="utf-8")
    calls: list[dict] = []
    extractor = SimpleNamespace(main=lambda **kwargs: calls.append(kwargs))
    fake_config = ModuleType("experiment_config")
    fake_config.SAMPLING_INTERVAL = "1s"  # type: ignore[attr-defined]
    fake_config.TIME_MODES = {  # type: ignore[attr-defined]
        "Midnight": ("00:00", "06:00"),
        "Morning": ("06:00", "10:00"),
        "Daytime": ("10:00", "18:00"),
        "Night": ("18:00", "24:00"),
    }
    fake_llm = ModuleType("src.behavior_pattern_mining.llm")
    fake_llm.pattern_extractor = extractor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "experiment_config", fake_config)
    monkeypatch.setitem(sys.modules, "src.behavior_pattern_mining.llm", fake_llm)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(
        sys,
        "argv",
        ["worker", "extract", "--research-root", str(tmp_path), "--run", str(run), "--run-id", "2"],
    )
    research_worker_main()
    assert calls[0]["run_ids"] == [2]
    assert calls[0]["input_modes_dir"] == run / "analysis/networks"
    assert calls[0]["days"] == 1
    assert extractor.PROMPT_TEMPLATE == "saved prompt"
    assert extractor.MODEL_NAME == "saved-model"
    assert extractor.TEMPERATURE == 0.12
    assert extractor.OUTPUT_FILE_PATH is None


def test_added_network_is_rejected_before_api_work(tmp_path: Path) -> None:
    run = synthetic_run(tmp_path)
    write_json(run / "analysis/networks/state_transition_Unexpected.json", {})
    with pytest.raises(ValueError, match="unexpected files"):
        extraction_budget(run)
