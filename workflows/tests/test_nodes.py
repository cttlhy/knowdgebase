from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import workflows.nodes as nodes_module


class WorkflowNodesTests(unittest.TestCase):
    def test_organize_node_filters_and_deduplicates(self) -> None:
        state = {
            "analyzed_items": [
                {"title": "A", "url": "https://example.com/a", "summary": "s1", "tags": ["ai"], "score": 0.8},
                {"title": "A-dup", "url": "https://example.com/a", "summary": "s2", "tags": ["llm"], "score": 0.9},
                {"title": "B", "url": "https://example.com/b", "summary": "s3", "tags": ["agent"], "score": 0.5},
            ],
            "iteration": 0,
        }

        update = nodes_module.organize_node(state)
        articles = update["articles"]

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["url"], "https://example.com/a")
        self.assertGreaterEqual(float(articles[0]["score"]), 0.6)

    def test_review_node_iteration_two_forces_pass(self) -> None:
        with patch.object(
            nodes_module,
            "chat_json",
            return_value=(
                {
                    "passed": False,
                    "overall_score": 0.1,
                    "feedback": "bad",
                    "scores": {
                        "summary_quality": 0.1,
                        "tag_accuracy": 0.1,
                        "classification_rationale": 0.1,
                        "consistency": 0.1,
                    },
                },
                nodes_module.Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
        ):
            update = nodes_module.review_node({"articles": [{"url": "https://example.com/a"}], "iteration": 2})

        self.assertTrue(update["review"]["passed"])

    def test_review_node_string_false_does_not_become_true(self) -> None:
        with patch.object(
            nodes_module,
            "chat_json",
            return_value=(
                {
                    "passed": "false",
                    "overall_score": 0.7,
                    "feedback": "not enough",
                    "scores": {
                        "summary_quality": 0.7,
                        "tag_accuracy": 0.7,
                        "classification_rationale": 0.7,
                        "consistency": 0.7,
                    },
                },
                nodes_module.Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
        ):
            update = nodes_module.review_node({"articles": [{"url": "https://example.com/a"}], "iteration": 0})

        self.assertFalse(update["review"]["passed"])

    def test_save_node_writes_article_files_and_index(self) -> None:
        articles = [
            {
                "id": "github-20260515-001",
                "title": "Demo Repo",
                "url": "https://github.com/example/demo",
                "summary": "summary",
                "tags": ["ai"],
                "score": 0.8,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            update = nodes_module.save_node({"articles": articles, "knowledge_root": str(root)})

            self.assertEqual(update["saved_count"], 1)
            articles_dir = root / "knowledge" / "articles"
            saved_files = list(articles_dir.glob("*.json"))
            self.assertEqual(len(saved_files), 2)  # article + index

            index_path = articles_dir / "index.json"
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(len(index_payload), 1)
            self.assertEqual(index_payload[0]["url"], "https://github.com/example/demo")

    def test_save_node_same_title_generates_unique_files(self) -> None:
        articles = [
            {"title": "Same Title", "url": "https://github.com/example/a", "summary": "a", "tags": ["ai"], "score": 0.9},
            {"title": "Same Title", "url": "https://github.com/example/b", "summary": "b", "tags": ["llm"], "score": 0.8},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            update = nodes_module.save_node({"articles": articles, "knowledge_root": str(root)})

            self.assertEqual(update["saved_count"], 2)
            articles_dir = root / "knowledge" / "articles"
            json_files = list(articles_dir.glob("*.json"))
            self.assertEqual(len(json_files), 3)  # 2 article files + index

    def test_collect_node_handles_network_error(self) -> None:
        with patch.object(nodes_module.urllib.request, "urlopen", side_effect=urllib.error.URLError("network down")):
            update = nodes_module.collect_node({"collect_limit": 2})

        self.assertEqual(update["raw_items"], [])
        self.assertIn("network down", update.get("collect_error", ""))


if __name__ == "__main__":
    unittest.main()
