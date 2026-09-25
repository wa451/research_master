"""Names and paths for Aruba sensor-representation experiment conditions."""

from __future__ import annotations

from pathlib import Path


SENSOR_REPRESENTATIONS = ("individual", "room")
DEFAULT_SENSOR_REPRESENTATION = "individual"


def validate_sensor_representation(representation: str) -> str:
    """Validate and normalize a supported Aruba sensor representation."""
    normalized = str(representation).strip().lower()
    if normalized not in SENSOR_REPRESENTATIONS:
        choices = ", ".join(SENSOR_REPRESENTATIONS)
        raise ValueError(f"Unknown sensor representation {representation!r}; choose one of: {choices}")
    return normalized


def sensor_map_path(project_root: Path, representation: str) -> Path:
    """Return the checked-in map for a representation condition."""
    representation = validate_sensor_representation(representation)
    filename = (
        "aruba_sensor_map_individual.json"
        if representation == "individual"
        else "aruba_sensor_map.json"
    )
    return project_root / "configs" / filename


def resolve_sensor_representation(
    representation: str | None,
    sensor_map: Path | None,
    project_root: Path,
) -> str:
    """Choose the default while recognizing the historical explicit room map."""
    if representation is not None:
        return validate_sensor_representation(representation)
    if sensor_map is not None and sensor_map.resolve() == sensor_map_path(
        project_root, "room"
    ).resolve():
        return "room"
    return DEFAULT_SENSOR_REPRESENTATION


def artifact_dataset_name(dataset: str, representation: str) -> str:
    """Namespace artifacts while preserving historical room-level Aruba paths."""
    representation = validate_sensor_representation(representation)
    return f"{dataset}_individual" if representation == "individual" else dataset
