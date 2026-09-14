"""Scenario loading for JSON and YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from smart_home_sim.errors import ScenarioError
from smart_home_sim.schema import Scenario


def load_scenario(path: str | Path, *, allowed_root: str | Path | None = None) -> Scenario:
    """Load a scenario, optionally restricting it and its inheritance chain to one root."""
    scenario_path = Path(path)
    root = Path(allowed_root).resolve() if allowed_root is not None else None
    try:
        raw = _load_raw_scenario(scenario_path, ancestors=(), allowed_root=root)
        return Scenario.model_validate(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ScenarioError(f"cannot parse scenario '{scenario_path}': {exc}") from exc
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ScenarioError(f"invalid scenario '{scenario_path}': {details}") from exc


def _load_raw_scenario(
    path: Path,
    *,
    ancestors: tuple[Path, ...],
    allowed_root: Path | None,
) -> dict[str, Any]:
    resolved = path.resolve()
    if allowed_root is not None and not resolved.is_relative_to(allowed_root):
        raise ScenarioError(f"scenario file is outside the allowed root: {path}")
    if not resolved.is_file():
        raise ScenarioError(f"scenario file does not exist: {path}")
    if resolved in ancestors:
        cycle = " -> ".join(str(item) for item in (*ancestors, resolved))
        raise ScenarioError(f"scenario inheritance cycle: {cycle}")
    suffix = resolved.suffix.lower()
    text = resolved.read_text(encoding="utf-8")
    if suffix == ".json":
        raw: Any = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        raw = yaml.safe_load(text)
    else:
        raise ScenarioError(f"unsupported scenario extension '{suffix}'; use .json, .yaml, or .yml")
    if not isinstance(raw, dict):
        raise ScenarioError(f"scenario root must be an object: {path}")
    parent_value = raw.pop("extends", None)
    if parent_value is None:
        return raw
    if not isinstance(parent_value, str) or not parent_value:
        raise ScenarioError(f"scenario 'extends' must be a non-empty path string: {path}")
    parent_path = (resolved.parent / parent_value).resolve()
    parent = _load_raw_scenario(
        parent_path,
        ancestors=(*ancestors, resolved),
        allowed_root=allowed_root,
    )
    return {**parent, **raw}
