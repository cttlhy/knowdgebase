from __future__ import annotations

import re
import unittest

import pipeline as pipeline_module


class PipelineOutputSchemaTests(unittest.TestCase):
    def test_organize_items_includes_required_validation_fields(self) -> None:
        analyzed_item = {
            "title": "demo project",
            "url": "https://github.com/example/demo",
            "source": "github",
            "date": "2026-05-13",
            "summary": "This is a long enough summary for validation checks.",
            "score": 8,
            "tags": ["llm"],
            "highlights": ["h1"],
        }

        organized = pipeline_module.organize_items([analyzed_item])

        self.assertEqual(len(organized), 1)
        article = organized[0]
        self.assertIn("id", article)
        self.assertIn("source_url", article)
        self.assertIn("status", article)
        self.assertEqual(article["source_url"], analyzed_item["url"])
        self.assertEqual(article["status"], "draft")
        self.assertRegex(article["id"], r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d{8}-\d{3}$")


if __name__ == "__main__":
    unittest.main()
