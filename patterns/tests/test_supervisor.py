from __future__ import annotations

import unittest
from unittest.mock import patch

from patterns.supervisor import supervisor


class SupervisorPatternTests(unittest.TestCase):
    def test_supervisor_returns_on_first_pass(self) -> None:
        mock_responses = [
            ('{"summary":"ok","risks":["none"]}', {"total_tokens": 10}),
            ('{"passed": true, "score": 9, "feedback": "good"}', {"total_tokens": 10}),
        ]

        with patch("patterns.supervisor.chat", side_effect=mock_responses):
            result = supervisor("分析这个任务")

        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["final_score"], 9)
        self.assertEqual(result["output"]["summary"], "ok")
        self.assertNotIn("warning", result)

    def test_supervisor_retries_with_feedback_until_passed(self) -> None:
        mock_responses = [
            ('{"summary":"v1"}', {"total_tokens": 10}),
            ('{"passed": false, "score": 5, "feedback": "增加细节"}', {"total_tokens": 10}),
            ('{"summary":"v2","details":["a","b"]}', {"total_tokens": 10}),
            ('{"passed": true, "score": 8, "feedback": "ok"}', {"total_tokens": 10}),
        ]

        with patch("patterns.supervisor.chat", side_effect=mock_responses) as chat_mock:
            result = supervisor("分析这个任务")

        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["final_score"], 8)
        self.assertEqual(result["output"]["summary"], "v2")

        worker_retry_call = chat_mock.call_args_list[2]
        worker_prompt = worker_retry_call.kwargs["messages"][1]["content"]
        self.assertIn("上一轮反馈", worker_prompt)
        self.assertIn("增加细节", worker_prompt)

    def test_supervisor_returns_warning_after_max_retries(self) -> None:
        mock_responses = [
            ('{"summary":"v1"}', {"total_tokens": 10}),
            ('{"passed": false, "score": 4, "feedback": "too shallow"}', {"total_tokens": 10}),
            ('{"summary":"v2"}', {"total_tokens": 10}),
            ('{"passed": false, "score": 6, "feedback": "still weak"}', {"total_tokens": 10}),
            ('{"summary":"v3"}', {"total_tokens": 10}),
            ('{"passed": false, "score": 6, "feedback": "not enough"}', {"total_tokens": 10}),
        ]

        with patch("patterns.supervisor.chat", side_effect=mock_responses):
            result = supervisor("分析这个任务", max_retries=3)

        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["final_score"], 6)
        self.assertIn("warning", result)
        self.assertEqual(result["output"]["summary"], "v3")


if __name__ == "__main__":
    unittest.main()
