from __future__ import annotations

import json
import importlib
import sys
import tempfile
import types
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

    def test_review_node_reviews_first_five_analyses_with_weighted_score(self) -> None:
        analyses = [
            {"title": f"analysis-{index}", "summary": "summary", "url": f"https://example.com/{index}"}
            for index in range(6)
        ]
        with patch.object(
            nodes_module,
            "chat_json",
            return_value=(
                {
                    "passed": False,
                    "overall_score": 10,
                    "feedback": "good enough",
                    "scores": {
                        "summary_quality": 8,
                        "technical_depth": 7,
                        "relevance": 8,
                        "originality": 6,
                        "formatting": 7,
                    },
                },
                nodes_module.Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            ),
        ) as chat_json_mock:
            update = nodes_module.review_node(
                {
                    "analyses": analyses,
                    "articles": [{"title": "must-not-review"}],
                    "iteration": 0,
                    "provider": "deepseek",
                }
            )

        prompt = chat_json_mock.call_args.kwargs["prompt"]
        self.assertIn("analysis-4", prompt)
        self.assertNotIn("analysis-5", prompt)
        self.assertNotIn("must-not-review", prompt)
        self.assertEqual(chat_json_mock.call_args.kwargs["temperature"], 0.1)
        self.assertTrue(update["review_passed"])
        self.assertAlmostEqual(update["review"]["overall_score"], 7.3)
        self.assertEqual(update["iteration"], 1)
        self.assertEqual(update["cost_tracker"]["total_tokens"], 150)
        self.assertGreater(update["cost_tracker"]["total_cost_usd"], 0)

    def test_review_node_recomputes_score_and_fails_below_threshold(self) -> None:
        with patch.object(
            nodes_module,
            "chat_json",
            return_value=(
                {
                    "passed": True,
                    "overall_score": 10,
                    "feedback": "not enough",
                    "scores": {
                        "summary_quality": 6,
                        "technical_depth": 6,
                        "relevance": 6,
                        "originality": 6,
                        "formatting": 6,
                    },
                },
                nodes_module.Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            ),
        ):
            update = nodes_module.review_node({"analyses": [{"url": "https://example.com/a"}], "iteration": 0})

        self.assertFalse(update["review_passed"])
        self.assertEqual(update["review"]["overall_score"], 6.0)

    def test_review_node_auto_passes_when_llm_fails(self) -> None:
        with patch.object(nodes_module, "chat_json", side_effect=RuntimeError("llm down")):
            update = nodes_module.review_node({"analyses": [{"url": "https://example.com/a"}], "iteration": 3})

        self.assertTrue(update["review_passed"])
        self.assertIn("LLM", update["review_feedback"])
        self.assertEqual(update["iteration"], 4)

    def test_review_wrapper_does_not_increment_iteration_twice(self) -> None:
        langgraph_module = types.ModuleType("langgraph")
        langgraph_graph_module = types.ModuleType("langgraph.graph")
        langgraph_graph_module.END = "__end__"
        langgraph_graph_module.StateGraph = object
        review_update = {
            "review_passed": True,
            "review_feedback": "ok",
            "iteration": 6,
            "cost_tracker": {},
        }
        with patch.dict(
            sys.modules,
            {"langgraph": langgraph_module, "langgraph.graph": langgraph_graph_module},
        ):
            graph_module = importlib.import_module("workflows.graph")
        with patch.object(graph_module, "review_node", return_value=review_update):
            update = graph_module._review_wrapper({"iteration": 5})

        self.assertEqual(update["iteration"], 6)
        self.assertTrue(update["review_passed"])

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
