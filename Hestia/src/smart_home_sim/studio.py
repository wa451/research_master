"""Local browser editor for Hestia scenarios."""

from __future__ import annotations

import json
import shutil
import threading
import webbrowser
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.errors import OutputValidationError, ScenarioError, SimulationInvariantError
from smart_home_sim.experiments.plan import Condition, ExperimentPlan, House
from smart_home_sim.experiments.scenarios import build_scenario
from smart_home_sim.schema import EditorLayout, Scenario, Weekday

_STATIC_DIR = Path(__file__).with_name("studio_static")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioRequest(StrictRequest):
    scenario: dict[str, Any]


class ImportRequest(StrictRequest):
    text: str
    format: Literal["json", "yaml"] | None = None
    source_filename: str | None = None


class ExportRequest(ScenarioRequest):
    format: Literal["json", "yaml"] = "yaml"


class ProjectSaveRequest(ScenarioRequest):
    filename: str
    overwrite: bool = False


class SimulationRunRequest(StrictRequest):
    scenario_path: str
    days: int
    seed: int
    output_name: str


def _weekly_routine(activity_id: str) -> dict[str, list[dict[str, Any]]]:
    return {
        day.value: [{"activity_id": activity_id, "scheduled_start_minute": 1080}] for day in Weekday
    }


def default_scenario() -> Scenario:
    """Build the small valid starter scenario shown by a fresh Studio session."""
    return Scenario.model_validate(
        {
            "schema_version": 1,
            "id": "my_home",
            "name": "My Hestia home",
            "start_datetime": "2025-01-06T00:00:00+09:00",
            "rooms": [
                {
                    "id": "living_room",
                    "name": "Living room",
                    "capacity": 2,
                    "devices": [
                        {"id": "M_LIVING", "type": "MotionSensor", "name": "Living motion"},
                        {"id": "L_LIVING", "type": "Light", "name": "Living light"},
                    ],
                },
                {
                    "id": "outside",
                    "name": "Outside",
                    "capacity": 10,
                    "is_outside": True,
                    "devices": [
                        {"id": "M_OUTSIDE", "type": "MotionSensor", "name": "Outside motion"}
                    ],
                },
            ],
            "connections": [{"source": "living_room", "target": "outside", "travel_seconds": 5}],
            "activities": [
                {
                    "id": "relaxing",
                    "name": "Relaxing",
                    "room_id": "living_room",
                    "base_duration_minutes": 60,
                    "variation_fraction": 0.1,
                    "device_actions": [{"device_id": "L_LIVING", "state": "ON"}],
                    "adl_label": "Relax",
                }
            ],
            "residents": [
                {
                    "id": "resident_1",
                    "name": "Haruko",
                    "initial_room_id": "living_room",
                    "priority": 0,
                    "duration_multiplier": 1.0,
                    "secondary_activity_factor": 1.0,
                    "weekly_routine": _weekly_routine("relaxing"),
                }
            ],
            "editor_layout": {
                "room_positions": {
                    "living_room": {"x": 10, "y": 20, "width": 38, "height": 48},
                    "outside": {"x": 62, "y": 34, "width": 24, "height": 28},
                },
                "device_positions": {
                    "M_LIVING": {"x": 22, "y": 66},
                    "L_LIVING": {"x": 66, "y": 45},
                    "M_OUTSIDE": {"x": 50, "y": 50},
                },
            },
        }
    )


_EVALUATION_HOUSE_ROOM_POSITIONS = {
    "compact": {
        "bathroom": (4, 5, 25, 30),
        "bedroom": (4, 55, 25, 35),
        "living": (36, 28, 28, 44),
        "kitchen": (71, 5, 25, 30),
        "outside": (71, 55, 25, 35),
    },
    "corridor": {
        "bathroom": (4, 4, 27, 24),
        "bedroom": (4, 38, 27, 24),
        "kitchen": (4, 72, 27, 24),
        "hallway": (39, 8, 22, 84),
        "living": (69, 4, 27, 24),
        "outside": (69, 38, 27, 24),
    },
    "branched": {
        "bathroom": (3, 4, 27, 24),
        "bedroom": (3, 38, 27, 24),
        "kitchen": (3, 72, 27, 24),
        "hallway": (39, 7, 20, 86),
        "outside": (70, 4, 27, 24),
        "living": (68, 38, 25, 24),
        "study": (70, 72, 27, 24),
    },
}


def evaluation_house_scenario(house: House) -> Scenario:
    """Build an editable Studio view of an evaluation-9 base house."""
    condition = Condition(id=f"{house}_base", house=house)
    plan = ExperimentPlan(conditions=[condition])
    scenario = build_scenario(condition, plan)
    room_positions = {
        room_id: {"x": x, "y": y, "width": width, "height": height}
        for room_id, (x, y, width, height) in _EVALUATION_HOUSE_ROOM_POSITIONS[house].items()
    }
    device_positions = {}
    position_grid = (
        (20, 35),
        (50, 35),
        (80, 35),
        (20, 68),
        (50, 68),
        (80, 68),
        (35, 84),
        (65, 84),
    )
    for room in scenario.rooms:
        for index, device in enumerate(room.devices):
            x, y = position_grid[index % len(position_grid)]
            device_positions[device.id] = {"x": x, "y": y}
    layout = EditorLayout.model_validate(
        {"room_positions": room_positions, "device_positions": device_positions}
    )
    return scenario.model_copy(
        update={
            "name": f"Evaluation 9 {house} base (Studio preset)",
            "editor_layout": layout,
        }
    )


def scenario_data(scenario: Scenario) -> dict[str, Any]:
    """Return JSON-compatible data while retaining the user's routine ordering."""
    return scenario.model_dump(mode="json", exclude_none=True)


def source_filename(value: str | None) -> str | None:
    """Keep only a display-safe filename; Studio never exposes a local path."""
    if not value:
        return None
    name = Path(value.replace("\\", "/")).name
    return name or None


def _error_response(status_code: int, path: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"valid": False, "errors": [{"path": path, "message": message}]},
    )


def _is_within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def _project_directory(project_root: Path, name: str) -> Path:
    directory = project_root / name
    directory.mkdir(parents=True, exist_ok=True)
    if not _is_within(directory, project_root):
        raise ValueError(f"project directory '{name}' must remain inside the project")
    return directory


def _safe_yaml_filename(value: str) -> str:
    filename = value.strip()
    if (
        not filename
        or filename in {".", ".."}
        or filename.startswith(".")
        or any(character in filename for character in ("/", "\\", "\x00", "\n", "\r"))
    ):
        raise ValueError("filename must be a non-hidden YAML basename")
    suffix = Path(filename).suffix.lower()
    if suffix not in {"", ".yaml", ".yml"}:
        raise ValueError("filename must use a .yaml or .yml extension")
    return filename if suffix else f"{filename}.yaml"


def _safe_output_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name in {".", ".."}
        or name.startswith(".")
        or any(character in name for character in ("/", "\\", "\x00", "\n", "\r"))
    ):
        raise ValueError("output name must be a non-hidden directory basename")
    return name


def _allowed_scenario_files(project_root: Path) -> dict[Path, str]:
    entries: dict[Path, str] = {}
    for directory_name in ("scenarios", "examples"):
        directory = project_root / directory_name
        if not directory.is_dir() or not _is_within(directory, project_root):
            continue
        for candidate in sorted(directory.rglob("*")):
            if candidate.suffix.lower() not in {".yaml", ".yml"} or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if not _is_within(resolved, project_root):
                continue
            entries[resolved] = resolved.relative_to(project_root).as_posix()
    return dict(sorted(entries.items(), key=lambda item: item[1]))


def _yaml_content(scenario: Scenario) -> str:
    return yaml.safe_dump(
        scenario_data(scenario),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _write_text_atomically(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validation_response(error: ValidationError) -> JSONResponse:
    errors = [
        {
            "path": ".".join(str(part) for part in item["loc"]) or "scenario",
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors(include_url=False)
    ]
    return JSONResponse(status_code=422, content={"valid": False, "errors": errors})


def _parse_scenario_source(text: str, source_format: str | None) -> dict[str, Any]:
    if source_format == "json":
        raw: Any = json.loads(text)
    elif source_format == "yaml":
        raw = yaml.safe_load(text)
    else:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("scenario root must be an object")
    if "extends" in raw:
        raise ValueError(
            "Studio import does not resolve 'extends'; launch Studio with --scenario instead"
        )
    return raw


def create_studio_app(
    initial_scenario: Scenario | None = None,
    *,
    initial_source_filename: str | None = None,
    initial_source_path: Path | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    """Create the local Studio app without starting a server."""
    if not _STATIC_DIR.is_dir():
        raise RuntimeError(f"Studio static assets are missing: {_STATIC_DIR}")

    root = (project_root or _PROJECT_ROOT).resolve()
    app = FastAPI(title="Hestia Studio", docs_url=None, redoc_url=None)
    initial = initial_scenario or default_scenario()
    initial_filename = source_filename(initial_source_filename)
    allowed_initial_paths = _allowed_scenario_files(root)
    initial_path = (
        allowed_initial_paths.get(initial_source_path.resolve())
        if initial_source_path is not None
        else None
    )
    run_lock = threading.Lock()
    reserved_output_paths: set[Path] = set()

    @app.get("/api/initial")
    def get_initial(evaluation_house: House | None = None) -> dict[str, Any]:
        if evaluation_house is not None:
            preset = evaluation_house_scenario(evaluation_house)
            return {
                "scenario": scenario_data(preset),
                "source_filename": f"{evaluation_house}_base.yaml",
                "source_path": None,
            }
        return {
            "scenario": scenario_data(initial),
            "source_filename": initial_filename,
            "source_path": initial_path,
        }

    @app.get("/api/template")
    def get_template() -> dict[str, Any]:
        return {
            "scenario": scenario_data(default_scenario()),
            "source_filename": None,
            "source_path": None,
        }

    @app.post("/api/import", response_model=None)
    def import_scenario(request: ImportRequest) -> dict[str, Any] | JSONResponse:
        try:
            scenario = Scenario.model_validate(_parse_scenario_source(request.text, request.format))
        except ValidationError as error:
            return _validation_response(error)
        except (json.JSONDecodeError, yaml.YAMLError, ValueError) as error:
            return JSONResponse(
                status_code=400,
                content={"valid": False, "errors": [{"path": "scenario", "message": str(error)}]},
            )
        return {
            "valid": True,
            "scenario": scenario_data(scenario),
            "source_filename": source_filename(request.source_filename),
            "source_path": None,
        }

    @app.post("/api/validate", response_model=None)
    def validate_scenario(request: ScenarioRequest) -> dict[str, Any] | JSONResponse:
        try:
            scenario = Scenario.model_validate(request.scenario)
        except ValidationError as error:
            return _validation_response(error)
        return {"valid": True, "scenario": scenario_data(scenario)}

    @app.post("/api/export", response_model=None)
    def export_scenario(request: ExportRequest) -> Response | JSONResponse:
        try:
            scenario = Scenario.model_validate(request.scenario)
        except ValidationError as error:
            return _validation_response(error)
        data = scenario_data(scenario)
        if request.format == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            media_type = "application/json"
            extension = "json"
        else:
            content = _yaml_content(scenario)
            media_type = "application/yaml"
            extension = "yaml"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{scenario.id}.{extension}"'},
        )

    @app.get("/api/project-scenarios")
    def list_project_scenarios() -> dict[str, Any]:
        files = _allowed_scenario_files(root)
        return {
            "files": [
                {
                    "path": relative_path,
                    "name": path.name,
                    "group": relative_path.split("/", maxsplit=1)[0],
                }
                for path, relative_path in files.items()
            ]
        }

    @app.post("/api/project-scenarios/save", response_model=None)
    def save_project_scenario(request: ProjectSaveRequest) -> dict[str, Any] | JSONResponse:
        try:
            scenario = Scenario.model_validate(request.scenario)
        except ValidationError as error:
            return _validation_response(error)
        try:
            filename = _safe_yaml_filename(request.filename)
            scenario_directory = _project_directory(root, "scenarios")
            destination = scenario_directory / filename
            if not _is_within(destination, root):
                raise ValueError("filename must remain inside scenarios")
        except ValueError as error:
            return _error_response(400, "filename", str(error))
        if destination.exists() and not request.overwrite:
            return _error_response(
                409,
                "filename",
                f"'{filename}' already exists; confirm overwrite to replace it",
            )
        try:
            _write_text_atomically(destination, _yaml_content(scenario))
        except OSError as error:
            return _error_response(500, "filename", f"could not save YAML: {error}")
        relative_path = destination.relative_to(root).as_posix()
        return {
            "valid": True,
            "filename": filename,
            "scenario_path": relative_path,
            "scenario": scenario_data(scenario),
        }

    @app.post("/api/simulations/run", response_model=None)
    def run_simulation(request: SimulationRunRequest) -> dict[str, Any] | JSONResponse:
        if not 1 <= request.days <= 365:
            return _error_response(422, "days", "days must be between 1 and 365")
        files = _allowed_scenario_files(root)
        paths_by_relative = {relative_path: path for path, relative_path in files.items()}
        scenario_path = paths_by_relative.get(request.scenario_path)
        if scenario_path is None:
            return _error_response(
                404, "scenario_path", "YAML file is not available for Studio runs"
            )
        try:
            scenario = load_scenario(scenario_path, allowed_root=root)
        except ScenarioError as error:
            return _error_response(422, "scenario_path", str(error))
        try:
            output_name = _safe_output_name(request.output_name)
            output_root = _project_directory(root, "outputs") / "studio"
            output_root.mkdir(parents=True, exist_ok=True)
            if not _is_within(output_root, root):
                raise ValueError("output directory must remain inside the project")
        except ValueError as error:
            return _error_response(400, "output_name", str(error))
        destination = output_root / output_name
        with run_lock:
            if destination.exists() or destination in reserved_output_paths:
                return _error_response(
                    409,
                    "output_name",
                    f"output directory '{output_name}' already exists; choose another name",
                )
            reserved_output_paths.add(destination)
        staging = output_root / f".{output_name}.running-{uuid4().hex}"
        try:
            result = SimulationEngine(scenario, days=request.days, seed=request.seed).run(staging)
            if destination.exists():
                raise FileExistsError(destination)
            staging.replace(destination)
        except FileExistsError:
            return _error_response(
                409,
                "output_name",
                f"output directory '{output_name}' already exists; choose another name",
            )
        except (SimulationInvariantError, OutputValidationError, ValueError, OSError) as error:
            return _error_response(422, "simulation", str(error))
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            with run_lock:
                reserved_output_paths.discard(destination)
        return {
            "valid": True,
            "scenario_path": request.scenario_path,
            "output_dir": destination.relative_to(root).as_posix(),
            "event_count": result.event_count,
            "simple_event_count": result.simple_event_count,
            "state_count": result.state_count,
            "aruba_count": result.aruba_count,
            "content_hash": result.content_hash,
            "validation": result.validation,
        }

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/assets", StaticFiles(directory=_STATIC_DIR), name="studio-assets")
    return app


def serve_studio(
    *,
    scenario_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Serve Studio locally, optionally opening the browser after Uvicorn starts."""
    initial_scenario = load_scenario(scenario_path) if scenario_path is not None else None
    url = f"http://{host}:{port}"
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    uvicorn.run(
        create_studio_app(
            initial_scenario,
            initial_source_filename=scenario_path.name if scenario_path is not None else None,
            initial_source_path=scenario_path,
        ),
        host=host,
        port=port,
        log_level="info",
    )
