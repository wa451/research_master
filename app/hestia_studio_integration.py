"""Lifecycle and URL helpers for the embedded local Hestia Studio server."""

from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.command_builder import command_preview
from app.utils import redact_text

STUDIO_HOST = "127.0.0.1"
EVALUATION_HOUSES = ("compact", "corridor", "branched")


@dataclass
class HestiaStudioProcess:
    process: subprocess.Popen[str]
    port: int
    log_path: Path
    command: list[str]

    @property
    def running(self) -> bool:
        return self.process.poll() is None


def hestia_studio_base_url(port: int) -> str:
    return f"http://{STUDIO_HOST}:{port}"


def hestia_studio_url(port: int, house: str) -> str:
    if house not in EVALUATION_HOUSES:
        raise ValueError(f"unknown evaluation house: {house}")
    query = urlencode({"evaluation_house": house})
    return f"{hestia_studio_base_url(port)}/?{query}"


def hestia_studio_command(hestia_root: Path, port: int) -> list[str]:
    executable = hestia_root / ".venv" / "bin" / "python"
    if not executable.is_file():
        raise FileNotFoundError(
            f"Hestia Python was not found at {executable}. Run 'uv sync' in Hestia first."
        )
    return [
        str(executable),
        "-m",
        "smart_home_sim.cli",
        "studio",
        "--host",
        STUDIO_HOST,
        "--port",
        str(port),
        "--no-open",
    ]


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.2)
        return connection.connect_ex((STUDIO_HOST, port)) == 0


def is_hestia_studio_ready(port: int, *, timeout: float = 0.25) -> bool:
    endpoint = f"{hestia_studio_base_url(port)}/api/initial?evaluation_house=compact"
    try:
        with urlopen(endpoint, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False
    scenario = payload.get("scenario") if isinstance(payload, dict) else None
    return isinstance(scenario, dict) and scenario.get("id") == "compact_base"


def _capture_output(process: subprocess.Popen[str], log_path: Path) -> None:
    if process.stdout is None:
        return
    with log_path.open("a", encoding="utf-8") as log_file:
        for line in process.stdout:
            log_file.write(redact_text(line))
            log_file.flush()


def start_hestia_studio(
    hestia_root: Path, port: int, *, log_path: Path
) -> HestiaStudioProcess:
    command = hestia_studio_command(hestia_root, port)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"$ {command_preview(command)}\n\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command,
        cwd=str(hestia_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=environment,
    )
    managed = HestiaStudioProcess(
        process=process,
        port=port,
        log_path=log_path,
        command=command,
    )
    threading.Thread(
        target=_capture_output,
        args=(process, log_path),
        name=f"hestia-studio-{port}-log",
        daemon=True,
    ).start()
    atexit.register(stop_hestia_studio, managed)
    return managed


def stop_hestia_studio(managed: HestiaStudioProcess) -> None:
    if not managed.running:
        return
    managed.process.terminate()
    try:
        managed.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        managed.process.kill()
        managed.process.wait(timeout=5)


def studio_log_tail(managed: HestiaStudioProcess, *, max_chars: int = 4000) -> str:
    if not managed.log_path.is_file():
        return ""
    return managed.log_path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
