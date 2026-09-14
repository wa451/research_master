from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from conftest import ROOT
from fastapi import FastAPI

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.schema import Scenario
from smart_home_sim.studio import create_studio_app, default_scenario, scenario_data


async def _request_async(
    app: FastAPI,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://studio.test") as client:
        return await client.request(method, path, json=payload)


def _request(
    app: FastAPI,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> httpx.Response:
    return asyncio.run(_request_async(app, method, path, payload))


def _output_directory_hash(output_dir: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        digest.update(path.relative_to(output_dir).as_posix().encode("utf-8"))
        digest.update(bytes([0]))
        digest.update(path.read_bytes())
        digest.update(bytes([0]))
    return digest.hexdigest()


def test_studio_serves_editor_and_validates_the_starter_scenario() -> None:
    app = create_studio_app()

    page = _request(app, "GET", "/")
    script = _request(app, "GET", "/assets/app.js")
    initial = _request(app, "GET", "/api/initial")
    validation = _request(app, "POST", "/api/validate", {"scenario": initial.json()["scenario"]})

    assert (
        page.status_code
        == script.status_code
        == initial.status_code
        == validation.status_code
        == 200
    )
    assert "Hestia Studio" in page.text
    assert 'id="gui-mode-button"' in page.text
    assert 'id="code-mode-button"' in page.text
    assert 'id="code-editor"' in page.text
    assert 'id="source-file-name"' in page.text
    assert 'id="run-pane"' in page.text
    assert 'id="save-yaml-button"' in page.text
    assert 'id="run-simulation-button"' in page.text
    assert "rooms" in page.text
    assert "residents" in page.text
    assert "function renderLayout" in script.text
    assert "function enterCodeMode" in script.text
    assert "function applyCode" in script.text
    assert "function saveCurrentYaml" in script.text
    assert "function saveErrorFallback" in script.text
    assert "Studioを停止してから再起動してください。" in script.text
    assert "function runSimulation" in script.text
    assert validation.json()["valid"] is True
    assert (
        validation.json()["scenario"]["editor_layout"]["room_positions"]["living_room"]["x"] == 10
    )
    assert initial.json()["source_filename"] is None


def test_studio_exposes_only_the_source_basename() -> None:
    app = create_studio_app(
        default_scenario(),
        initial_source_filename="examples\\homes/aruba_single_resident.yaml",
    )
    data = scenario_data(default_scenario())

    initial = _request(app, "GET", "/api/initial")
    imported = _request(
        app,
        "POST",
        "/api/import",
        {
            "text": json.dumps(data),
            "format": "json",
            "source_filename": "/private/scenarios/uploaded_home.json",
        },
    )

    assert initial.status_code == imported.status_code == 200
    assert initial.json()["source_filename"] == "aruba_single_resident.yaml"
    assert imported.json()["source_filename"] == "uploaded_home.json"


def test_studio_returns_field_errors_for_invalid_editor_layout() -> None:
    app = create_studio_app()
    data = scenario_data(default_scenario())
    data["editor_layout"]["room_positions"]["missing_room"] = {
        "x": 0,
        "y": 0,
        "width": 10,
        "height": 10,
    }

    response = _request(app, "POST", "/api/validate", {"scenario": data})

    assert response.status_code == 422
    payload = response.json()
    assert payload["valid"] is False
    assert "unknown rooms" in payload["errors"][0]["message"]


def test_studio_import_and_export_round_trip_yaml() -> None:
    app = create_studio_app()
    data = scenario_data(default_scenario())
    data["name"] = "編集済みホーム"

    imported = _request(
        app,
        "POST",
        "/api/import",
        {"text": json.dumps(data, ensure_ascii=False), "format": "json"},
    )
    exported = _request(
        app,
        "POST",
        "/api/export",
        {"scenario": imported.json()["scenario"], "format": "yaml"},
    )

    assert imported.status_code == 200
    assert imported.json()["valid"] is True
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/yaml")
    assert "attachment; filename=" in exported.headers["content-disposition"]
    restored = Scenario.model_validate(yaml.safe_load(exported.text))
    assert restored.name == "編集済みホーム"
    assert restored.editor_layout is not None


def test_studio_saves_yaml_inside_the_project_and_requires_overwrite_confirmation(
    tmp_path: Path,
) -> None:
    app = create_studio_app(default_scenario(), project_root=tmp_path)
    data = scenario_data(default_scenario())

    saved = _request(
        app,
        "POST",
        "/api/project-scenarios/save",
        {"scenario": data, "filename": "studio_home.yaml"},
    )
    repeated = _request(
        app,
        "POST",
        "/api/project-scenarios/save",
        {"scenario": data, "filename": "studio_home.yaml"},
    )
    updated_data = deepcopy(data)
    updated_data["name"] = "Updated Studio home"
    overwritten = _request(
        app,
        "POST",
        "/api/project-scenarios/save",
        {"scenario": updated_data, "filename": "studio_home.yaml", "overwrite": True},
    )
    listed = _request(app, "GET", "/api/project-scenarios")

    destination = tmp_path / "scenarios" / "studio_home.yaml"
    assert saved.status_code == 200
    assert saved.json()["scenario_path"] == "scenarios/studio_home.yaml"
    assert destination.is_file()
    assert load_scenario(destination).editor_layout is not None
    assert repeated.status_code == 409
    assert overwritten.status_code == 200
    assert load_scenario(destination).name == "Updated Studio home"
    assert listed.json()["files"] == [
        {"path": "scenarios/studio_home.yaml", "name": "studio_home.yaml", "group": "scenarios"}
    ]


@pytest.mark.parametrize(
    "filename",
    ["../escape.yaml", "nested/home.yaml", "/tmp/home.yaml", "..\\escape.yaml", "home.json"],
)
def test_studio_rejects_unsafe_project_save_filenames(tmp_path: Path, filename: str) -> None:
    app = create_studio_app(default_scenario(), project_root=tmp_path)

    response = _request(
        app,
        "POST",
        "/api/project-scenarios/save",
        {"scenario": scenario_data(default_scenario()), "filename": filename},
    )

    assert response.status_code == 400
    assert not (tmp_path / "scenarios").exists()


def test_studio_runs_a_selected_saved_yaml_without_overwriting_outputs(tmp_path: Path) -> None:
    app = create_studio_app(default_scenario(), project_root=tmp_path)
    saved = _request(
        app,
        "POST",
        "/api/project-scenarios/save",
        {"scenario": scenario_data(default_scenario()), "filename": "run_home.yaml"},
    )
    first_run = _request(
        app,
        "POST",
        "/api/simulations/run",
        {
            "scenario_path": saved.json()["scenario_path"],
            "days": 1,
            "seed": 73,
            "output_name": "first",
        },
    )
    second_run = _request(
        app,
        "POST",
        "/api/simulations/run",
        {
            "scenario_path": saved.json()["scenario_path"],
            "days": 1,
            "seed": 73,
            "output_name": "repeat",
        },
    )
    collision = _request(
        app,
        "POST",
        "/api/simulations/run",
        {
            "scenario_path": saved.json()["scenario_path"],
            "days": 1,
            "seed": 74,
            "output_name": "first",
        },
    )

    output_dir = tmp_path / "outputs" / "studio" / "first"
    assert saved.status_code == first_run.status_code == second_run.status_code == 200
    assert first_run.json()["output_dir"] == "outputs/studio/first"
    assert (output_dir / "events.csv").is_file()
    assert (output_dir / "manifest.json").is_file()
    assert first_run.json()["content_hash"] == second_run.json()["content_hash"]
    assert collision.status_code == 409


def test_studio_rejects_invalid_run_inputs_before_execution(tmp_path: Path) -> None:
    app = create_studio_app(default_scenario(), project_root=tmp_path)

    bad_path = _request(
        app,
        "POST",
        "/api/simulations/run",
        {"scenario_path": "../outside.yaml", "days": 1, "seed": 1, "output_name": "escape"},
    )
    bad_days = _request(
        app,
        "POST",
        "/api/simulations/run",
        {"scenario_path": "scenarios/missing.yaml", "days": 0, "seed": 1, "output_name": "zero"},
    )

    assert bad_path.status_code == 404
    assert bad_days.status_code == 422
    assert not (tmp_path / "outputs").exists()


def test_studio_run_rejects_inheritance_outside_the_project(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scenario_dir = project_root / "scenarios"
    scenario_dir.mkdir(parents=True)
    outside = tmp_path / "outside.yaml"
    outside.write_text(yaml.safe_dump(scenario_data(default_scenario())), encoding="utf-8")
    (scenario_dir / "unsafe.yaml").write_text("extends: ../../outside.yaml\n", encoding="utf-8")
    app = create_studio_app(default_scenario(), project_root=project_root)

    response = _request(
        app,
        "POST",
        "/api/simulations/run",
        {
            "scenario_path": "scenarios/unsafe.yaml",
            "days": 1,
            "seed": 1,
            "output_name": "unsafe",
        },
    )

    assert response.status_code == 422
    assert "outside the allowed root" in response.json()["errors"][0]["message"]
    assert not (project_root / "outputs").exists()


@pytest.mark.parametrize("source_format", ["json", "yaml"])
def test_code_edit_import_preserves_editor_layout(source_format: str) -> None:
    app = create_studio_app()
    data = scenario_data(default_scenario())
    data["name"] = "コードで編集したホーム"
    expected_layout = deepcopy(data["editor_layout"])
    text = (
        json.dumps(data, ensure_ascii=False)
        if source_format == "json"
        else yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    )

    imported = _request(
        app,
        "POST",
        "/api/import",
        {"text": text, "format": source_format},
    )

    assert imported.status_code == 200
    assert imported.json()["valid"] is True
    assert imported.json()["scenario"]["name"] == "コードで編集したホーム"
    assert imported.json()["scenario"]["editor_layout"] == expected_layout


def test_editor_layout_does_not_change_the_model_when_omitted() -> None:
    data = scenario_data(default_scenario())
    without_layout = deepcopy(data)
    without_layout.pop("editor_layout")

    scenario = Scenario.model_validate(without_layout)

    assert scenario.editor_layout is None


def test_editor_layout_does_not_change_complete_simulation_outputs(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT / "examples/aruba_single_resident.yaml")
    with_layout_data = scenario.model_dump(mode="json")
    with_layout_data["editor_layout"] = {
        "room_positions": {
            "bedroom": {"x": 8, "y": 10, "width": 28, "height": 30},
        },
        "device_positions": {"M001": {"x": 25, "y": 55}},
    }
    with_layout = Scenario.model_validate(with_layout_data)

    baseline = SimulationEngine(scenario, days=1, seed=73).run(tmp_path / "without_layout")
    positioned = SimulationEngine(with_layout, days=1, seed=73).run(tmp_path / "with_layout")

    assert _output_directory_hash(baseline.output_dir) == _output_directory_hash(
        positioned.output_dir
    )
