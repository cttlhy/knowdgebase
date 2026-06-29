from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_model_client = types.ModuleType("pipeline.model_client")
sys.modules.setdefault("pipeline.model_client", _model_client)

import scripts.distribute_daily_articles as distribute_script
from workflows.distribution import format_daily_digest


class DistributeDailyArticlesTests(unittest.TestCase):
    def test_collect_daily_articles_picks_top_scored_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            articles_dir = Path(tmp)
            high = {
                "id": "github-20260628-001",
                "title": "High",
                "source_url": "https://github.com/example/high",
                "summary": "High score AI agent article for distribution test.",
                "score": 9,
                "tags": ["ai", "agent"],
            }
            low = {
                "id": "github-20260628-002",
                "title": "Low",
                "source_url": "https://github.com/example/low",
                "summary": "Low score AI agent article for distribution test.",
                "score": 3,
                "tags": ["ai", "agent"],
            }
            (articles_dir / "20260628-high.json").write_text(json.dumps(high), encoding="utf-8")
            (articles_dir / "20260628-low.json").write_text(json.dumps(low), encoding="utf-8")

            articles = distribute_script.collect_daily_articles(
                articles_dir,
                date_stamp="20260628",
                limit=1,
                send_all=False,
                only_new=True,
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "High")

    def test_collect_daily_articles_skips_already_sent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            articles_dir = Path(tmp)
            sent = {
                "id": "github-20260628-001",
                "title": "Sent",
                "source_url": "https://github.com/example/sent",
                "summary": "Already sent AI article for distribution test.",
                "score": 9,
                "tags": ["ai", "agent"],
                "distribution": {"telegram": False, "feishu": True},
            }
            (articles_dir / "20260628-sent.json").write_text(json.dumps(sent), encoding="utf-8")

            articles = distribute_script.collect_daily_articles(
                articles_dir,
                date_stamp="20260628",
                limit=5,
                send_all=False,
                only_new=True,
            )

        self.assertEqual(articles, [])

    def test_format_daily_digest_builds_single_message(self) -> None:
        from workflows.distribution import format_daily_digest

        digest = format_daily_digest(
            [
                {
                    "title": "High",
                    "summary": "High score AI agent article for distribution test.",
                    "score": 0.9,
                    "source_url": "https://github.com/example/high",
                    "tags": ["ai", "agent"],
                }
            ],
            date_stamp="20260629",
            total_count=12,
            digest_limit=5,
        )

        self.assertIn("AI 知识库日报 | 2026-06-29", digest)
        self.assertIn("今日收录 12 条", digest)
        self.assertIn("High", digest)
        self.assertIn("https://github.com/example/high", digest)
        self.assertEqual(digest.count("\n1. "), 1)


if __name__ == "__main__":
    unittest.main()
