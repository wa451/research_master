"""Focused checks for dashboard whole-batch progress labels."""

from __future__ import annotations

import unittest

from app.streamlit_app import batch_progress_text


class BatchProgressTextTests(unittest.TestCase):
    def test_includes_completed_total_and_current_step(self) -> None:
        self.assertEqual(
            batch_progress_text(2, 5, "3. 評価を実行"),
            "進捗: 2/5 ステップ完了 / 実行中: 3. 評価を実行",
        )

    def test_completed_batch_has_no_running_step(self) -> None:
        self.assertEqual(batch_progress_text(5, 5), "進捗: 5/5 ステップ完了")


if __name__ == "__main__":
    unittest.main()
