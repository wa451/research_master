"""Staged experiment CLI. Only extract --allow-api can call a paid model."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from smart_home_sim.experiments.artifacts import generate, select_runs, write_json
from smart_home_sim.experiments.duration import (
    DEFAULT_TRAIN_DAYS,
    generate_duration,
    score_duration,
)
from smart_home_sim.experiments.evaluation import frequency_baseline, score_runs, write_summary
from smart_home_sim.experiments.plan import Condition, ExperimentPlan, load_plan
from smart_home_sim.experiments.research import extract as extract_run
from smart_home_sim.experiments.research import extraction_budget
from smart_home_sim.experiments.research import prepare as prepare_run

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    help="Noise-free multi-home research evaluation (no API calls by default).",
)
ConditionOption = Annotated[str | None, typer.Option(help="Select a single condition ID")]
SeedOption = Annotated[int | None, typer.Option(help="Select a single simulation seed")]


def _duration_values(value: str) -> list[int]:
    try:
        return [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise typer.BadParameter("train days must be comma-separated integers") from exc


@app.command("plan")
def make_plan(
    output: Annotated[Path, typer.Option(help="New JSON plan path")],
    pilot: Annotated[
        bool, typer.Option(help="One seed, two train + two test days in each house")
    ] = False,
) -> None:
    """Write an editable plan without running simulations or using an API."""
    if output.exists():
        raise typer.BadParameter(f"refusing to overwrite {output}")
    plan = ExperimentPlan()
    if pilot:
        plan = ExperimentPlan(
            train_days=2,
            test_days=2,
            seeds=[11],
            llm_runs=1,
            conditions=[
                Condition(id=f"{house}_base", house=house)
                for house in ("compact", "corridor", "branched")
            ]
            + [Condition(id="compact_two", house="compact", residents=2)],
        )
    write_json(output, plan.model_dump(mode="json"))
    typer.echo(
        f"{len(plan.conditions)} conditions x {len(plan.seeds)} seeds x {plan.days} days. "
        f"Wrote {output}; no API calls."
    )


@app.command("generate")
def generate_command(
    plan: Annotated[Path, typer.Argument(help="JSON/YAML experiment plan")],
    output: Annotated[Path, typer.Option(help="New experiment output directory")],
) -> None:
    """Generate sensor-only inputs and separate truth for every condition/seed."""
    runs = generate(load_plan(plan), output)
    typer.echo(
        f"Generated/verified {len(runs)} simulation runs in {output}; observation noise OFF."
    )


@app.command("duration-generate")
def duration_generate_command(
    plan: Annotated[Path, typer.Argument(help="35-day duration experiment plan")],
    output: Annotated[Path, typer.Option(help="New duration experiment directory")],
    train_days: Annotated[str, typer.Option(help="Trailing train windows")] = ",".join(
        str(value) for value in DEFAULT_TRAIN_DAYS
    ),
) -> None:
    """Generate raw logs once and derive paired train-duration windows."""
    runs = generate_duration(load_plan(plan), output, _duration_values(train_days))
    typer.echo(f"Generated/verified {len(runs)} duration analysis windows in {output}.")


@app.command("duration-evaluate")
def duration_evaluate_command(
    experiment: Path,
    output_dir: Annotated[Path, typer.Option(help="Duration summary directory")],
    method: Annotated[Literal["frequency", "llm", "both"], typer.Option()] = "both",
    llm_results_root: Annotated[
        Path | None,
        typer.Option(help="Model-specific root containing duration LLM artifacts"),
    ] = None,
) -> None:
    """Score every duration window and write paired summaries and plots."""
    rows = score_duration(experiment, output_dir, method, llm_results_root)
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("complete", "missing", "invalid")
    }
    typer.echo(f"{counts}; summary={output_dir / 'evaluation9_duration_summary.csv'}")
    if counts["invalid"]:
        raise typer.Exit(code=2)


@app.command("prepare")
def prepare_command(
    experiment: Path,
    research_root: Annotated[
        Path, typer.Option(help="Existing master-research repository with .venv")
    ],
    condition: ConditionOption = None,
    seed: SeedOption = None,
) -> None:
    """Build training states/networks with existing code, then map held-out logs."""
    for run in select_runs(experiment, condition, seed):
        typer.echo(f"Preparing {run.parent.name}/{run.name}")
        prepare_run(run, research_root)
    typer.echo("Preparation complete; no API calls.")


@app.command("baseline")
def baseline_command(
    experiment: Path, condition: ConditionOption = None, seed: SeedOption = None
) -> None:
    """Run a training-only contiguous-frequency control (not the proposed method)."""
    for run in select_runs(experiment, condition, seed):
        frequency_baseline(run)
    typer.echo("Frequency control complete; no API calls.")


@app.command("extract")
def extract_command(
    experiment: Path,
    research_root: Annotated[Path, typer.Option(help="Existing master-research repository")],
    allow_api: Annotated[bool, typer.Option(help="Explicitly permit paid LLM API calls")] = False,
    llm_results_root: Annotated[
        Path | None,
        typer.Option(help="Model-specific root for LLM outputs and checkpoints"),
    ] = None,
    model_id: Annotated[
        str | None,
        typer.Option(help="Active provider model ID for workload reporting"),
    ] = None,
    condition: ConditionOption = None,
    seed: SeedOption = None,
) -> None:
    """Show the extraction workload; --allow-api opts into actual model calls."""
    runs = select_runs(experiment, condition, seed)
    for run in runs:
        artifact_run = (
            llm_results_root / run.relative_to(experiment)
            if llm_results_root is not None
            else run
        )
        budget = extraction_budget(run, artifact_run)
        typer.echo(
            f"{run.parent.name}/{run.name}: model={model_id or budget['model']}, "
            f"temperature={budget['temperature']}, modes={budget['modes']}, "
            f"pending repetitions={len(budget['pending_run_ids'])}, "
            f"fresh calls ≤{budget['fresh_mode_calls_upper_bound']} "
            f"(parse attempts ≤{budget['parse_attempts_upper_bound']}; "
            "backend transport retries may add requests)."
        )
    if not allow_api:
        typer.echo("Dry run only. To call the model, rerun with --allow-api. No API calls made.")
        return
    for run in runs:
        artifact_run = (
            llm_results_root / run.relative_to(experiment)
            if llm_results_root is not None
            else run
        )
        extract_run(run, research_root, artifact_run, model_id)


@app.command("evaluate")
def evaluate_command(
    experiment: Path,
    method: Annotated[Literal["frequency", "llm", "both"], typer.Option()] = "both",
    condition: ConditionOption = None,
    seed: SeedOption = None,
    summary: Annotated[
        Path | None, typer.Option(help="Summary stem; .json and .csv are written")
    ] = None,
    llm_results_root: Annotated[
        Path | None,
        typer.Option(help="Model-specific root containing LLM outputs and checkpoints"),
    ] = None,
) -> None:
    """Score held-out recovery/ADL and report missing runs without treating them as zeros."""
    runs = select_runs(experiment, condition, seed)
    rows = []
    artifact_runs = (
        {run: llm_results_root / run.relative_to(experiment) for run in runs}
        if llm_results_root is not None
        else None
    )
    for selected in ["frequency", "llm"] if method == "both" else [method]:
        rows.extend(score_runs(runs, selected, artifact_runs))
    target = summary or experiment / "evaluation" / (
        f"summary_{method}_{condition or 'all'}_{seed if seed is not None else 'all'}"
    )
    write_summary(target, rows)
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("complete", "missing", "invalid")
    }
    typer.echo(f"{counts}; summary={target.with_suffix('.csv')}")
    if counts["invalid"]:
        raise typer.Exit(code=2)
