from __future__ import annotations

import csv
from pathlib import Path

from conftest import ROOT
from typer.testing import CliRunner

from smart_home_sim.cli import app
from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.events import EVENT_COLUMNS
from smart_home_sim.outputs import CasasPreset, export_aruba

runner = CliRunner()


def test_cli_validation_success_and_contextual_error() -> None:
    success = runner.invoke(app, ["validate", str(ROOT / "examples/aruba_single_resident.yaml")])
    missing = runner.invoke(app, ["validate", "missing.yaml"])
    assert success.exit_code == 0
    assert "Valid scenario 'aruba_single_resident'" in success.stdout
    assert missing.exit_code == 2
    assert "scenario file does not exist" in missing.output
    assert "Traceback" not in missing.output


def test_transform_state_and_aruba_cli(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    simulation = SimulationEngine(scenario, days=1, seed=5).run(tmp_path / "source")
    events = simulation.output_dir / "events.csv"
    state_path = tmp_path / "state.csv"
    aruba_path = tmp_path / "aruba.txt"

    state_result = runner.invoke(app, ["transform-state", str(events), "--output", str(state_path)])
    aruba_result = runner.invoke(app, ["export-aruba", str(events), "--output", str(aruba_path)])
    assert state_result.exit_code == aruba_result.exit_code == 0
    with state_path.open(encoding="utf-8", newline="") as stream:
        state_rows = list(csv.DictReader(stream))
    assert state_rows
    assert "occupants" in state_rows[0]
    assert "active_activities" in state_rows[0]
    first_aruba = aruba_path.read_text(encoding="utf-8").splitlines()[0]
    assert len(first_aruba.split(maxsplit=4)) == 5


def test_casas_motion_door_preset_is_pipeline_compatible(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    simulation = SimulationEngine(scenario, days=1, seed=5).run(tmp_path / "source")
    output = tmp_path / "casas.txt"

    result = runner.invoke(
        app,
        [
            "export-aruba",
            str(simulation.output_dir / "events.csv"),
            "--output",
            str(output),
            "--preset",
            "motion-door",
        ],
    )

    assert result.exit_code == 0
    lines = [line.split() for line in output.read_text(encoding="utf-8").splitlines()]
    device_ids = {device.id for room in scenario.rooms for device in room.devices}
    assert lines
    assert all(len(parts) in {4, 6} for parts in lines)
    assert all(parts[2].startswith("activity::") or parts[2] in device_ids for parts in lines)
    assert any(parts[-1] == "begin" for parts in lines)
    assert any(parts[-1] == "end" for parts in lines)
    assert all(parts[3] in {"ON", "OFF", "OPEN", "CLOSE", "START", "END"} for parts in lines)

    without_boundaries = tmp_path / "casas_no_boundaries.txt"
    export_aruba(
        simulation.output_dir / "events.csv",
        without_boundaries,
        preset=CasasPreset.MOTION_DOOR,
        include_activity_boundaries=False,
    )
    assert all(
        len(line.split()) == 4
        for line in without_boundaries.read_text(encoding="utf-8").splitlines()
    )


def test_casas_preset_rejects_unsupported_state(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    simulation = SimulationEngine(scenario, days=1, seed=5).run(tmp_path / "source")
    source = simulation.output_dir / "events.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    motion = next(row for row in rows if row["device_type"] == "MotionSensor")
    motion["state"] = "PRESENT"
    malformed = tmp_path / "malformed_events.csv"
    with malformed.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    try:
        export_aruba(malformed, tmp_path / "bad.txt", preset=CasasPreset.MOTION_DOOR)
    except ValueError as exc:
        assert "unsupported CASAS state 'PRESENT'" in str(exc)
    else:
        raise AssertionError("unsupported state was accepted")


def test_transform_rejects_missing_columns(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.csv"
    malformed.write_text("timestamp,state\n2025-01-01T00:00:00+00:00,ON\n", encoding="utf-8")
    result = runner.invoke(
        app, ["transform-state", str(malformed), "--output", str(tmp_path / "out.csv")]
    )
    assert result.exit_code == 2
    assert "missing required columns" in result.output
    assert set(EVENT_COLUMNS) - {"timestamp", "state"}
