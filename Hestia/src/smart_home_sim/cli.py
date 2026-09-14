"""Non-interactive command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.errors import (
    OutputValidationError,
    ScenarioError,
    SimulationInvariantError,
)
from smart_home_sim.experiments.cli import app as experiment_app
from smart_home_sim.outputs import CasasPreset, transform_state_csv
from smart_home_sim.outputs import export_aruba as export_aruba_file
from smart_home_sim.studio import serve_studio

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
    help="Reproducible smart-home activity and sensor-log simulator.",
)
app.add_typer(experiment_app, name="experiment")


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=2)


@app.command()
def validate(
    scenario: Annotated[Path, typer.Argument(help="JSON or YAML scenario file")],
) -> None:
    """Parse and validate a scenario without running it."""
    try:
        loaded = load_scenario(scenario)
    except ScenarioError as exc:
        _fail(str(exc))
    typer.echo(
        f"Valid scenario '{loaded.id}': {len(loaded.rooms)} rooms, "
        f"{len(loaded.residents)} residents, {len(loaded.activities)} activities"
    )


@app.command()
def simulate(
    scenario: Annotated[Path, typer.Argument(help="JSON or YAML scenario file")],
    days: Annotated[int, typer.Option("--days", min=1)] = 7,
    seed: Annotated[int, typer.Option("--seed")] = 42,
    output: Annotated[Path, typer.Option("--output", help="Output directory")] = Path(
        "outputs/run"
    ),
) -> None:
    """Run a scenario and write every supported output format."""
    try:
        loaded = load_scenario(scenario)
        result = SimulationEngine(loaded, days=days, seed=seed).run(output)
    except (ScenarioError, SimulationInvariantError, OutputValidationError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(
        f"Simulation complete: {result.event_count} events, {result.state_count} states, "
        f"sha256={result.content_hash}, output={result.output_dir}"
    )


@app.command()
def studio(
    scenario: Annotated[
        Path | None,
        typer.Option("--scenario", "-s", help="Optional JSON or YAML scenario to edit"),
    ] = None,
    host: Annotated[str, typer.Option("--host", help="Local host to bind")] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535, help="Local port to bind"),
    ] = 8765,
    no_open: Annotated[
        bool,
        typer.Option("--no-open", help="Do not open a browser automatically"),
    ] = False,
) -> None:
    """Open the visual scenario editor in a local browser."""
    try:
        serve_studio(
            scenario_path=scenario,
            host=host,
            port=port,
            open_browser=not no_open,
        )
    except ScenarioError as exc:
        _fail(str(exc))


@app.command("transform-state")
def transform_state(
    events: Annotated[Path, typer.Argument(help="Raw events CSV")],
    output: Annotated[Path, typer.Option("--output", help="State-vector CSV")],
) -> None:
    """Transform raw events into wide state vectors."""
    try:
        count = transform_state_csv(events, output)
    except (OSError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(f"Wrote {count} state vectors to {output}")


@app.command("export-aruba")
def export_aruba(
    events: Annotated[Path, typer.Argument(help="Raw events CSV")],
    output: Annotated[Path, typer.Option("--output", help="Aruba/CASAS-style text log")],
    preset: Annotated[
        CasasPreset,
        typer.Option("--preset", help="Export profile: legacy, motion-door, or all-devices"),
    ] = CasasPreset.LEGACY,
    activity_boundaries: Annotated[
        bool | None,
        typer.Option(
            "--activity-boundaries/--no-activity-boundaries",
            help="Include six-field ADL begin/end records (preset default when omitted)",
        ),
    ] = None,
) -> None:
    """Export raw events in Aruba/CASAS-like four-field format."""
    try:
        count = export_aruba_file(
            events,
            output,
            preset=preset,
            include_activity_boundaries=activity_boundaries,
        )
    except (OSError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(f"Wrote {count} Aruba/CASAS-style events to {output}")


if __name__ == "__main__":
    app()
