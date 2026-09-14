"""Streamlit Components v2 adapter for the Hestia Studio editor."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import streamlit as st
from smart_home_sim.experiments.plan import House
from smart_home_sim.studio_service import StudioResult, StudioService
from streamlit.components import v2 as components

from app.command_builder import PROJECT_ROOT

HESTIA_ROOT = PROJECT_ROOT / "Hestia"
STATIC_ROOT = HESTIA_ROOT / "src" / "smart_home_sim" / "studio_static"
COMPONENT_KEY = "hestia_studio_editor"
RESPONSE_KEY = "_hestia_studio_component_response"
EVALUATION_HOUSES: tuple[House, ...] = ("compact", "corridor", "branched")


def _component_html() -> str:
    source = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    body = source.split("<body>", maxsplit=1)[1].split("</body>", maxsplit=1)[0]
    return re.sub(
        r"\s*<script\b[^>]*\bsrc=\"/assets/app\.js\"[^>]*></script>\s*", "", body
    )


HESTIA_STUDIO_COMPONENT = components.component(
    "research_master.hestia_studio",
    html=_component_html(),
    css=(STATIC_ROOT / "styles.css").read_text(encoding="utf-8"),
    js=(STATIC_ROOT / "app.js").read_text(encoding="utf-8"),
    isolate_styles=True,
)


@lru_cache(maxsize=4)
def _service(project_root: str) -> StudioService:
    return StudioService(project_root=Path(project_root))


def _bootstrap(service: StudioService) -> dict[str, Any]:
    houses: dict[House, dict[str, Any]] = {}
    for house in EVALUATION_HOUSES:
        initial_result = service.initial(house)
        assert isinstance(initial_result.body, dict)
        houses[house] = initial_result.body
    files_result = service.list_project_scenarios()
    assert isinstance(files_result.body, dict)
    return {
        "initial_house": "compact",
        "houses": houses,
        "template": service.template().body,
        "files": files_result.body["files"],
    }


def _payload(request: dict[str, Any]) -> dict[str, Any]:
    body = request.get("body")
    return body if isinstance(body, dict) else {}


def dispatch_studio_request(
    service: StudioService, request: dict[str, Any]
) -> StudioResult:
    """Route a component trigger to the transport-independent Hestia service."""
    parsed = urlparse(str(request.get("path", "")))
    path = parsed.path
    body = _payload(request)
    if path == "/api/initial":
        house = parse_qs(parsed.query).get("evaluation_house", [None])[0]
        if house is not None and house not in EVALUATION_HOUSES:
            return StudioResult(
                status_code=422,
                body={
                    "valid": False,
                    "errors": [
                        {"path": "evaluation_house", "message": "unknown house"}
                    ],
                },
            )
        return service.initial(cast(House | None, house))
    if path == "/api/template":
        return service.template()
    if path == "/api/import":
        source_format = body.get("format")
        if source_format not in {None, "json", "yaml"}:
            return StudioResult(
                status_code=422,
                body={
                    "valid": False,
                    "errors": [{"path": "format", "message": "invalid format"}],
                },
            )
        return service.import_scenario(
            str(body.get("text", "")), source_format, body.get("source_filename")
        )
    if path == "/api/validate":
        return service.validate_scenario(body.get("scenario", {}))
    if path == "/api/export":
        source_format = body.get("format", "yaml")
        if source_format not in {"json", "yaml"}:
            return StudioResult(
                status_code=422,
                body={
                    "valid": False,
                    "errors": [{"path": "format", "message": "invalid format"}],
                },
            )
        return service.export_scenario(body.get("scenario", {}), source_format)
    if path == "/api/project-scenarios":
        return service.list_project_scenarios()
    if path == "/api/project-scenarios/save":
        return service.save_project_scenario(
            body.get("scenario", {}),
            str(body.get("filename", "")),
            overwrite=bool(body.get("overwrite", False)),
        )
    if path == "/api/simulations/run":
        try:
            return service.run_simulation(
                str(body.get("scenario_path", "")),
                int(body.get("days", 0)),
                int(body.get("seed", 0)),
                str(body.get("output_name", "")),
            )
        except (TypeError, ValueError):
            return StudioResult(
                status_code=422,
                body={
                    "valid": False,
                    "errors": [
                        {"path": "simulation", "message": "invalid run options"}
                    ],
                },
            )
    return StudioResult(
        status_code=404,
        body={
            "valid": False,
            "errors": [{"path": "request", "message": "unknown action"}],
        },
    )


def _component_response(
    service: StudioService, request: dict[str, Any]
) -> dict[str, Any]:
    request_id = str(request.get("id", ""))
    try:
        result = dispatch_studio_request(service, request)
        return {
            "id": request_id,
            "ok": result.ok,
            "status": result.status_code,
            "body": result.body,
            "media_type": result.media_type,
        }
    except Exception:  # noqa: BLE001  # pragma: no cover - defensive UI boundary
        return {
            "id": request_id,
            "ok": False,
            "status": 500,
            "body": {
                "valid": False,
                "errors": [{"path": "studio", "message": "Studio operation failed"}],
            },
            "media_type": "application/json",
        }


def render_hestia_studio_component(project_root: Path = HESTIA_ROOT) -> Any:
    """Mount Hestia Studio directly in the Streamlit page without an iframe."""
    service = _service(str(project_root.resolve()))

    def handle_request() -> None:
        component_state = st.session_state.get(COMPONENT_KEY, {})
        request = component_state.get("request") if component_state else None
        if isinstance(request, dict):
            st.session_state[RESPONSE_KEY] = _component_response(service, request)

    component_state = st.session_state.get(COMPONENT_KEY, {})
    workspace = component_state.get("workspace") if component_state else None
    response = st.session_state.pop(RESPONSE_KEY, None)
    return HESTIA_STUDIO_COMPONENT(
        key=COMPONENT_KEY,
        data={
            "bootstrap": _bootstrap(service),
            "workspace": workspace,
            "response": response,
        },
        default={"workspace": workspace},
        height=1100,
        width="stretch",
        on_workspace_change=lambda: None,
        on_request_change=handle_request,
    )
