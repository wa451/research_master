"""Tests for the embedded Hestia Studio launcher contract."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.hestia_studio_integration import (
    hestia_studio_command,
    hestia_studio_url,
)


class HestiaStudioIntegrationTests(unittest.TestCase):
    def test_embedded_frame_uses_supported_streamlit_arguments(self):
        from app.streamlit_app import render_hestia_studio_frame

        with patch("app.streamlit_app.st.iframe") as iframe:
            render_hestia_studio_frame("http://127.0.0.1:8765/")

        iframe.assert_called_once_with("http://127.0.0.1:8765/", height=980)

    def test_house_urls_select_the_three_evaluation_presets(self):
        self.assertEqual(
            hestia_studio_url(8765, "compact"),
            "http://127.0.0.1:8765/?evaluation_house=compact",
        )
        self.assertEqual(
            hestia_studio_url(9000, "branched"),
            "http://127.0.0.1:9000/?evaluation_house=branched",
        )
        with self.assertRaises(ValueError):
            hestia_studio_url(8765, "unknown")

    def test_launcher_uses_hestia_venv_without_a_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / ".venv" / "bin" / "python"
            executable.parent.mkdir(parents=True)
            executable.touch()

            command = hestia_studio_command(root, 8765)

            self.assertEqual(command[0], str(executable))
            self.assertEqual(command[1:4], ["-m", "smart_home_sim.cli", "studio"])
            self.assertEqual(
                command[-5:], ["--host", "127.0.0.1", "--port", "8765", "--no-open"]
            )

    def test_launcher_reports_an_unprepared_hestia_environment(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(FileNotFoundError, "uv sync"),
        ):
            hestia_studio_command(Path(directory), 8765)


if __name__ == "__main__":
    unittest.main()
