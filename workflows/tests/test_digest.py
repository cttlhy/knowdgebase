from __future__ import annotations

import unittest

from workflows.distribution import format_daily_digest


class DailyDigestFormatTests(unittest.TestCase):
    def test_format_daily_digest_includes_top_items_and_total_count(self) -> None:
        digest = format_daily_digest(
            [
                {
                    "title": "Alpha",
                    "summary": "First article summary for digest formatting test.",
                    "score": 0.91,
                    "source_url": "https://github.com/example/alpha",
                    "tags": ["ai"],
                },
                {
                    "title": "Beta",
                    "summary": "Second article summary for digest formatting test.",
                    "score": 0.82,
                    "url": "https://github.com/example/beta",
                    "tags": ["agent"],
                },
            ],
            date_stamp="20260629",
            total_count=18,
            digest_limit=2,
        )

        self.assertIn("精选 Top 2", digest)
        self.assertIn("今日收录 18 条", digest)
        self.assertIn("Alpha", digest)
        self.assertIn("Beta", digest)
        self.assertLessEqual(len(digest), 3800)


if __name__ == "__main__":
    unittest.main()
