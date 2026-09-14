"""Transport-independent services shared by Hestia Studio frontends."""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import yaml
from pydantic import ValidationError

from smart_home_sim.config import load_scenario
from smart_home_sim.engine import SimulationEngine
from smart_home_sim.errors import OutputValidationError, ScenarioError, SimulationInvariantError
from smart_home_sim.experiments.plan import Condition, ExperimentPlan, House
from smart_home_sim.experiments.scenarios import build_scenario
from smart_home_sim.schema import EditorLayout, Scenario, Weekday

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StudioResult:
    """Frontend-neutral result with HTTP-compatible status metadata."""

    body: dict[str, Any] | str
    status_code: int = 200
    media_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


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
    scenario = build_scenario(condition, ExperimentPlan(conditions=[condition]))
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
            if _is_within(resolved, project_root):
                entries[resolved] = resolved.relative_to(project_root).as_posix()
    return dict(sorted(entries.items(), key=lambda item: item[1]))


def _yaml_content(scenario: Scenario) -> str:
    return yaml.safe_dump(
        scenario_data(scenario), allow_unicode=True, default_flow_style=False, sort_keys=False
    )


def _write_text_atomically(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validation_errors(error: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "path": ".".join(str(part) for part in item["loc"]) or "scenario",
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors(include_url=False)
    ]


def _error(status_code: int, path: str, message: str) -> StudioResult:
    return StudioResult(
        status_code=status_code,
        body={"valid": False, "errors": [{"path": path, "message": message}]},
    )


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


class StudioService:
    """Validate, persist, convert, and run Studio scenarios without a web transport."""

    def __init__(
        self,
        initial_scenario: Scenario | None = None,
        *,
        initial_source_filename: str | None = None,
        initial_source_path: Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.root = (project_root or PROJECT_ROOT).resolve()
        self.initial_scenario = initial_scenario or default_scenario()
        self.initial_filename = source_filename(initial_source_filename)
        allowed_initial_paths = _allowed_scenario_files(self.root)
        self.initial_path = (
            allowed_initial_paths.get(initial_source_path.resolve())
            if initial_source_path is not None
            else None
        )
        self.run_lock = threading.Lock()
        self.reserved_output_paths: set[Path] = set()

    def initial(self, evaluation_house: House | None = None) -> StudioResult:
        scenario = (
            evaluation_house_scenario(evaluation_house)
            if evaluation_house is not None
            else self.initial_scenario
        )
        return StudioResult(
            body={
                "scenario": scenario_data(scenario),
                "source_filename": (
                    f"{evaluation_house}_base.yaml"
                    if evaluation_house is not None
                    else self.initial_filename
                ),
                "source_path": None if evaluation_house is not None else self.initial_path,
            }
        )

    def template(self) -> StudioResult:
        return StudioResult(
            body={
                "scenario": scenario_data(default_scenario()),
                "source_filename": None,
                "source_path": None,
            }
        )

    def import_scenario(
        self,
        text: str,
        source_format: Literal["json", "yaml"] | None = None,
        source_name: str | None = None,
    ) -> StudioResult:
        try:
            scenario = Scenario.model_validate(_parse_scenario_source(text, source_format))
        except ValidationError as error:
            return StudioResult(
                status_code=422, body={"valid": False, "errors": _validation_errors(error)}
            )
        except (json.JSONDecodeError, yaml.YAMLError, ValueError) as error:
            return _error(400, "scenario", str(error))
        return StudioResult(
            body={
                "valid": True,
                "scenario": scenario_data(scenario),
                "source_filename": source_filename(source_name),
                "source_path": None,
            }
        )

    def validate_scenario(self, data: dict[str, Any]) -> StudioResult:
        try:
            scenario = Scenario.model_validate(data)
        except ValidationError as error:
            return StudioResult(
                status_code=422, body={"valid": False, "errors": _validation_errors(error)}
            )
        return StudioResult(body={"valid": True, "scenario": scenario_data(scenario)})

    def export_scenario(
        self, data: dict[str, Any], source_format: Literal["json", "yaml"] = "yaml"
    ) -> StudioResult:
        try:
            scenario = Scenario.model_validate(data)
        except ValidationError as error:
            return StudioResult(
                status_code=422, body={"valid": False, "errors": _validation_errors(error)}
            )
        if source_format == "json":
            content = json.dumps(scenario_data(scenario), ensure_ascii=False, indent=2) + "\n"
            media_type = "application/json"
            extension = "json"
        else:
            content = _yaml_content(scenario)
            media_type = "application/yaml"
            extension = "yaml"
        return StudioResult(
            body=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{scenario.id}.{extension}"'},
        )

    def list_project_scenarios(self) -> StudioResult:
        files = _allowed_scenario_files(self.root)
        return StudioResult(
            body={
                "files": [
                    {
                        "path": relative_path,
                        "name": path.name,
                        "group": relative_path.split("/", maxsplit=1)[0],
                    }
                    for path, relative_path in files.items()
                ]
            }
        )

    def save_project_scenario(
        self, data: dict[str, Any], filename: str, *, overwrite: bool = False
    ) -> StudioResult:
        try:
            scenario = Scenario.model_validate(data)
        except ValidationError as error:
            return StudioResult(
                status_code=422, body={"valid": False, "errors": _validation_errors(error)}
            )
        try:
            safe_filename = _safe_yaml_filename(filename)
            destination = _project_directory(self.root, "scenarios") / safe_filename
            if not _is_within(destination, self.root):
                raise ValueError("filename must remain inside scenarios")
        except ValueError as error:
            return _error(400, "filename", str(error))
        if destination.exists() and not overwrite:
            return _error(
                409,
                "filename",
                f"'{safe_filename}' already exists; confirm overwrite to replace it",
            )
        try:
            _write_text_atomically(destination, _yaml_content(scenario))
        except OSError as error:
            return _error(500, "filename", f"could not save YAML: {error}")
        relative_path = destination.relative_to(self.root).as_posix()
        return StudioResult(
            body={
                "valid": True,
                "filename": safe_filename,
                "scenario_path": relative_path,
                "scenario": scenario_data(scenario),
            }
        )

    def run_simulation(
        self, scenario_path: str, days: int, seed: int, output_name: str
    ) -> StudioResult:
        if not 1 <= days <= 365:
            return _error(422, "days", "days must be between 1 and 365")
        files = _allowed_scenario_files(self.root)
        paths_by_relative = {relative_path: path for path, relative_path in files.items()}
        source = paths_by_relative.get(scenario_path)
        if source is None:
            return _error(404, "scenario_path", "YAML file is not available for Studio runs")
        try:
            scenario = load_scenario(source, allowed_root=self.root)
        except ScenarioError as error:
            return _error(422, "scenario_path", str(error))
        try:
            safe_output_name = _safe_output_name(output_name)
            output_root = _project_directory(self.root, "outputs") / "studio"
            output_root.mkdir(parents=True, exist_ok=True)
            if not _is_within(output_root, self.root):
                raise ValueError("output directory must remain inside the project")
        except ValueError as error:
            return _error(400, "output_name", str(error))
        destination = output_root / safe_output_name
        with self.run_lock:
            if destination.exists() or destination in self.reserved_output_paths:
                return _error(
                    409,
                    "output_name",
                    f"output directory '{safe_output_name}' already exists; choose another name",
                )
            self.reserved_output_paths.add(destination)
        staging = output_root / f".{safe_output_name}.running-{uuid4().hex}"
        try:
            result = SimulationEngine(scenario, days=days, seed=seed).run(staging)
            if destination.exists():
                raise FileExistsError(destination)
            staging.replace(destination)
        except FileExistsError:
            return _error(
                409,
                "output_name",
                f"output directory '{safe_output_name}' already exists; choose another name",
            )
        except (SimulationInvariantError, OutputValidationError, ValueError, OSError) as error:
            return _error(422, "simulation", str(error))
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            with self.run_lock:
                self.reserved_output_paths.discard(destination)
        return StudioResult(
            body={
                "valid": True,
                "scenario_path": scenario_path,
                "output_dir": destination.relative_to(self.root).as_posix(),
                "event_count": result.event_count,
                "simple_event_count": result.simple_event_count,
                "state_count": result.state_count,
                "aruba_count": result.aruba_count,
                "content_hash": result.content_hash,
                "validation": result.validation,
            }
        )
