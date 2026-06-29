from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from workflows.cost_guard import BudgetExceededError, CostGuard


@dataclass
class UsageLike:
    prompt_tokens: int
    completion_tokens: int


class CostGuardTests(unittest.TestCase):
    def test_record_tracks_usage_and_cost_by_node(self) -> None:
        guard = CostGuard(
            budget=10.0,
            input_price_per_million=1.0,
            output_price_per_million=2.0,
        )

        guard.record(
            "planner",
            {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
            model="test-model",
            provider="deepseek",
        )

        report = guard.get_report()
        self.assertEqual(report["total_prompt_tokens"], 1_000_000)
        self.assertEqual(report["total_completion_tokens"], 500_000)
        self.assertEqual(report["total_cost"], 2.0)
        self.assertEqual(report["nodes"]["planner"]["call_count"], 1)
        self.assertEqual(report["nodes"]["planner"]["models"], {"test-model": 1})
        self.assertEqual(report["nodes"]["planner"]["providers"], {"deepseek": 1})

    def test_record_accepts_usage_objects(self) -> None:
        guard = CostGuard(budget=1.0)

        record = guard.record("reviewer", UsageLike(prompt_tokens=1000, completion_tokens=500))

        self.assertEqual(record.prompt_tokens, 1000)
        self.assertEqual(record.completion_tokens, 500)

    def test_record_raises_when_budget_is_exceeded_by_default(self) -> None:
        guard = CostGuard(budget=0.01)

        with self.assertRaises(BudgetExceededError):
            guard.record("reviewer", {"prompt_tokens": 20_000, "completion_tokens": 0})

        self.assertEqual(guard.get_status().status, "exceeded")

    def test_warning_status_does_not_raise_before_budget_is_exceeded(self) -> None:
        guard = CostGuard(budget=1.0, alert_threshold=0.8)

        status = guard.record("writer", {"prompt_tokens": 800_000, "completion_tokens": 0})

        self.assertEqual(status.cost, 0.8)
        self.assertEqual(guard.check().status, "warning")

    def test_can_disable_automatic_budget_enforcement(self) -> None:
        guard = CostGuard(budget=0.01, enforce_on_record=False)

        guard.record("reviewer", {"prompt_tokens": 20_000, "completion_tokens": 0})

        self.assertEqual(guard.get_status().status, "exceeded")
        with self.assertRaises(BudgetExceededError):
            guard.check()

    def test_rejects_invalid_configuration_and_usage(self) -> None:
        with self.assertRaises(ValueError):
            CostGuard(budget=0)
        with self.assertRaises(ValueError):
            CostGuard(alert_threshold=1.1)
        with self.assertRaises(ValueError):
            CostGuard(input_price_per_million=-1)

        guard = CostGuard()
        with self.assertRaises(ValueError):
            guard.record("", {"prompt_tokens": 1, "completion_tokens": 1})
        with self.assertRaises(ValueError):
            guard.record("planner", {"prompt_tokens": -1, "completion_tokens": 1})
        with self.assertRaises(ValueError):
            guard.record("planner", {"prompt_tokens": "bad", "completion_tokens": 1})

    def test_save_report_writes_json(self) -> None:
        guard = CostGuard(budget=1.0)
        guard.record("planner", {"prompt_tokens": 1000, "completion_tokens": 0})

        with tempfile.TemporaryDirectory() as tmp:
            path = guard.save_report(Path(tmp) / "reports" / "cost.json")

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"]["status"], "ok")
            self.assertEqual(payload["records"][0]["node_name"], "planner")


if __name__ == "__main__":
    unittest.main()
