"""Standalone FastAPI transport for the reusable Hestia Studio services."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from smart_home_sim.config import load_scenario
from smart_home_sim.experiments.plan import House
from smart_home_sim.schema import Scenario
from smart_home_sim.studio_service import (
    StudioResult,
    StudioService,
    default_scenario,
    evaluation_house_scenario,
    scenario_data,
    source_filename,
)

__all__ = [
    "create_studio_app",
    "default_scenario",
    "evaluation_house_scenario",
    "scenario_data",
    "serve_studio",
    "source_filename",
]

_STATIC_DIR = Path(__file__).with_name("studio_static")


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


def _response(result: StudioResult) -> dict[str, Any] | Response:
    if isinstance(result.body, str):
        return Response(
            content=result.body,
            status_code=result.status_code,
            media_type=result.media_type,
            headers=result.headers,
        )
    if result.ok:
        return result.body
    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers=result.headers,
    )


def create_studio_app(
    initial_scenario: Scenario | None = None,
    *,
    initial_source_filename: str | None = None,
    initial_source_path: Path | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    """Create the optional standalone Studio app without starting a server."""
    if not _STATIC_DIR.is_dir():
        raise RuntimeError(f"Studio static assets are missing: {_STATIC_DIR}")

    service = StudioService(
        initial_scenario,
        initial_source_filename=initial_source_filename,
        initial_source_path=initial_source_path,
        project_root=project_root,
    )
    app = FastAPI(title="Hestia Studio", docs_url=None, redoc_url=None)

    @app.get("/api/initial", response_model=None)
    def get_initial(evaluation_house: House | None = None) -> dict[str, Any] | Response:
        return _response(service.initial(evaluation_house))

    @app.get("/api/template", response_model=None)
    def get_template() -> dict[str, Any] | Response:
        return _response(service.template())

    @app.post("/api/import", response_model=None)
    def import_scenario(request: ImportRequest) -> dict[str, Any] | Response:
        return _response(
            service.import_scenario(request.text, request.format, request.source_filename)
        )

    @app.post("/api/validate", response_model=None)
    def validate_scenario(request: ScenarioRequest) -> dict[str, Any] | Response:
        return _response(service.validate_scenario(request.scenario))

    @app.post("/api/export", response_model=None)
    def export_scenario(request: ExportRequest) -> dict[str, Any] | Response:
        return _response(service.export_scenario(request.scenario, request.format))

    @app.get("/api/project-scenarios", response_model=None)
    def list_project_scenarios() -> dict[str, Any] | Response:
        return _response(service.list_project_scenarios())

    @app.post("/api/project-scenarios/save", response_model=None)
    def save_project_scenario(request: ProjectSaveRequest) -> dict[str, Any] | Response:
        return _response(
            service.save_project_scenario(
                request.scenario, request.filename, overwrite=request.overwrite
            )
        )

    @app.post("/api/simulations/run", response_model=None)
    def run_simulation(request: SimulationRunRequest) -> dict[str, Any] | Response:
        return _response(
            service.run_simulation(
                request.scenario_path,
                request.days,
                request.seed,
                request.output_name,
            )
        )

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
    """Serve the optional standalone Studio CLI for backward compatibility."""
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
