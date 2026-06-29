from __future__ import annotations

import unittest
from unittest.mock import patch

from workflows.planner import plan_strategy, planner_node


class PlannerTests(unittest.TestCase):
    def test_plan_strategy_uses_lite_for_targets_below_ten(self) -> None:
        plan = plan_strategy(9)

        self.assertEqual(plan["strategy"], "lite")
        self.assertEqual(plan["per_source_limit"], 5)
        self.assertEqual(plan["relevance_threshold"], 0.7)
        self.assertEqual(plan["max_iterations"], 1)
        self.assertIn("目标", plan["rationale"])

    def test_plan_strategy_uses_standard_for_targets_from_ten_to_nineteen(self) -> None:
        plan = plan_strategy(10)

        self.assertEqual(plan["strategy"], "standard")
        self.assertEqual(plan["per_source_limit"], 10)
        self.assertEqual(plan["relevance_threshold"], 0.5)
        self.assertEqual(plan["max_iterations"], 2)

    def test_plan_strategy_uses_full_for_targets_at_least_twenty(self) -> None:
        plan = plan_strategy(20)

        self.assertEqual(plan["strategy"], "full")
        self.assertEqual(plan["per_source_limit"], 20)
        self.assertEqual(plan["relevance_threshold"], 0.4)
        self.assertEqual(plan["max_iterations"], 3)

    def test_plan_strategy_reads_default_target_from_environment(self) -> None:
        with patch.dict("os.environ", {"PLANNER_TARGET_COUNT": "21"}):
            plan = plan_strategy()

        self.assertEqual(plan["strategy"], "full")

    def test_plan_strategy_defaults_to_ten_when_environment_is_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            plan = plan_strategy()

        self.assertEqual(plan["strategy"], "standard")

    def test_planner_node_returns_plan_update(self) -> None:
        update = planner_node({"target_count": 8})

        self.assertEqual(update["plan"]["strategy"], "lite")
        self.assertEqual(update["collect_limit"], 5)
        self.assertEqual(update["max_iterations"], 1)
        self.assertEqual(update["relevance_threshold"], 0.7)


if __name__ == "__main__":
    unittest.main()
