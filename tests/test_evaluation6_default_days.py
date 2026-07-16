from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_6_compare_adl_interpretation_set.py"
SPEC = importlib.util.spec_from_file_location("evaluation6", SCRIPT_PATH)
assert SPEC and SPEC.loader
evaluation6 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation6)


class Evaluation6DefaultDaysTests(unittest.TestCase):
    def test_default_condition_uses_14_days(self) -> None:
        with patch.object(sys, "argv", [str(SCRIPT_PATH)]):
            args = evaluation6.parse_args()

        self.assertEqual(args.days, 14)
        self.assertIn("15_1_14days", str(args.patterns_proposed))
        self.assertIn("llm_direct_15_1_14days", str(args.patterns_direct))
        self.assertIn("6_adl_evaluation_14", str(args.state_series))


if __name__ == "__main__":
    unittest.main()
