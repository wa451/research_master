import unittest
from pathlib import Path
from unittest.mock import patch


class ReviewerResponseDashboardTests(unittest.TestCase):
    def test_discovers_only_completed_reviewer_response_bundles(self):
        from app.streamlit_app import reviewer_response_result_dirs

        root = Path("/tmp/reviewer-response-results")
        completed = root / "complete"
        incomplete = root / "incomplete"
        with patch("app.streamlit_app.PROJECT_ROOT", Path("/tmp")):
            with patch("pathlib.Path.exists", return_value=True), patch(
                "pathlib.Path.rglob",
                return_value=[
                    completed / "reviewer_response_evaluation_summary.json",
                    incomplete / "other.json",
                ],
            ):
                self.assertEqual(reviewer_response_result_dirs(), [completed])
