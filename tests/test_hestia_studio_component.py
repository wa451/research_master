"""Tests for the native Streamlit Components v2 Hestia Studio adapter."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from smart_home_sim.studio_service import StudioService

from app.hestia_studio_component import (
    EVALUATION_HOUSES,
    STATIC_ROOT,
    _bootstrap,
    dispatch_studio_request,
)
from app.streamlit_app import render_hestia_studio


class HestiaStudioComponentTests(unittest.TestCase):
    def test_component_reuses_the_studio_assets_and_v2_renderer(self):
        script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        page = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        streamlit_source = Path("app/streamlit_app.py").read_text(encoding="utf-8")

        self.assertIn("export default function renderHestiaStudioComponent", script)
        self.assertIn('componentBridge.setStateValue("workspace"', script)
        self.assertIn('componentBridge.setTriggerValue("request"', script)
        self.assertIn('id="floorplan"', page)
        self.assertNotIn("st.iframe", streamlit_source)
        self.assertNotIn("8765", streamlit_source)
        self.assertNotIn("subprocess", streamlit_source)

    def test_bootstrap_contains_all_three_editable_houses(self):
        with tempfile.TemporaryDirectory() as directory:
            service = StudioService(project_root=Path(directory))
            bootstrap = _bootstrap(service)

        self.assertEqual(tuple(bootstrap["houses"]), EVALUATION_HOUSES)
        self.assertEqual(
            [
                bootstrap["houses"][house]["scenario"]["id"]
                for house in EVALUATION_HOUSES
            ],
            ["compact_base", "corridor_base", "branched_base"],
        )

    def test_component_dispatch_validates_and_saves_through_shared_service(self):
        with tempfile.TemporaryDirectory() as directory:
            service = StudioService(project_root=Path(directory))
            initial_body = service.initial("compact").body
            self.assertIsInstance(initial_body, dict)
            assert isinstance(initial_body, dict)
            scenario = initial_body["scenario"]
            validated = dispatch_studio_request(
                service,
                {"path": "/api/validate", "body": {"scenario": scenario}},
            )
            saved = dispatch_studio_request(
                service,
                {
                    "path": "/api/project-scenarios/save",
                    "body": {"scenario": scenario, "filename": "component_home.yaml"},
                },
            )
            listed = dispatch_studio_request(
                service, {"path": "/api/project-scenarios"}
            )
            simulated = dispatch_studio_request(
                service,
                {
                    "path": "/api/simulations/run",
                    "body": {
                        "scenario_path": "scenarios/component_home.yaml",
                        "days": 1,
                        "seed": 7,
                        "output_name": "component_run",
                    },
                },
            )

            self.assertTrue(validated.ok)
            self.assertTrue(saved.ok)
            self.assertIsInstance(saved.body, dict)
            self.assertIsInstance(listed.body, dict)
            self.assertIsInstance(simulated.body, dict)
            assert isinstance(saved.body, dict)
            assert isinstance(listed.body, dict)
            assert isinstance(simulated.body, dict)
            self.assertEqual(
                saved.body["scenario_path"], "scenarios/component_home.yaml"
            )
            self.assertEqual(
                listed.body["files"][0]["path"], "scenarios/component_home.yaml"
            )
            self.assertTrue(simulated.ok)
            self.assertEqual(
                simulated.body["output_dir"], "outputs/studio/component_run"
            )
            self.assertGreater(simulated.body["event_count"], 0)

    def test_dashboard_mounts_component_without_start_controls(self):
        with (
            patch("app.streamlit_app.st.subheader"),
            patch("app.streamlit_app.st.caption"),
            patch("app.streamlit_app.st.info"),
            patch("app.streamlit_app.render_hestia_studio_component") as component,
        ):
            render_hestia_studio({})

        component.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
