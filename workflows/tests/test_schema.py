from __future__ import annotations

import unittest

from workflows.schema import (
    build_index_entry,
    canonicalize_article,
    normalize_score,
    validate_article_schema,
    validate_index_entry,
)


class SchemaContractTests(unittest.TestCase):
    def test_canonicalize_article_maps_legacy_fields(self) -> None:
        article = canonicalize_article(
            {
                "title": "Demo Repo",
                "url": "https://github.com/example/demo",
                "source": "github",
                "date": "2026-05-17T02:22:17.123532+00:00",
                "summary": "A useful AI agent workflow repository for testing.",
                "tags": ["ai", "agent"],
                "score": 8,
                "language": "Python",
                "popularity": "stars:100",
            },
            index=1,
            now="2026-05-17T02:22:47.962438+00:00",
        )

        self.assertEqual(article["source_url"], "https://github.com/example/demo")
        self.assertEqual(article["url"], "https://github.com/example/demo")
        self.assertEqual(article["collected_at"], "2026-05-17T02:22:17.123532+00:00")
        self.assertEqual(article["status"], "published")
        self.assertEqual(article["score"], 0.8)
        self.assertEqual(article["distribution"], {"telegram": False, "feishu": False})
        self.assertEqual(article["metadata"]["language"], "Python")

    def test_build_index_entry_projects_canonical_fields(self) -> None:
        article = canonicalize_article(
            {
                "title": "Demo Repo",
                "url": "https://github.com/example/demo",
                "source": "github",
                "summary": "A useful AI agent workflow repository for testing.",
                "tags": ["ai", "agent"],
                "score": 0.8,
            },
            index=2,
            now="2026-05-17T02:22:47.962438+00:00",
        )
        entry = build_index_entry(article, filename="demo.json", now="2026-05-17T02:22:47.962438+00:00")

        self.assertEqual(entry["source_url"], article["source_url"])
        self.assertEqual(entry["status"], "published")
        self.assertFalse(validate_index_entry(entry))

    def test_validate_article_schema_rejects_incomplete_payload(self) -> None:
        failures = validate_article_schema({"title": "x", "summary": "too short", "tags": ["ai"], "score": 0.5})
        self.assertIn("missing_id", failures)
        self.assertIn("summary_too_short", failures)
        self.assertIn("not_enough_tags", failures)

    def test_normalize_score_accepts_legacy_ten_point_scale(self) -> None:
        self.assertEqual(normalize_score(8), 0.8)
        self.assertEqual(normalize_score(0.75), 0.75)


if __name__ == "__main__":
    unittest.main()
