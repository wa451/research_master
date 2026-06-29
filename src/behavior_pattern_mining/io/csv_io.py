"""Shared I/O helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    """Write rows to a CSV file with headers."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
