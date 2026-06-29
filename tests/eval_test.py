from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from workflows.schema import (
    CANONICAL_ARTICLE_FIELDS,
    CANONICAL_INDEX_FIELDS,
    normalize_score,
    resolve_source_url,
    validate_article_schema,
    validate_index_entry,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT_DIR / "knowledge" / "articles"
INDEX_FILE = ARTICLES_DIR / "index.json"
HUMAN_FLAGS_DIR = ROOT_DIR / "human_flags"

MIN_INDEXED_ARTICLES = 1
MIN_ARTICLE_SCORE = 0.7
MIN_SUMMARY_CHARS = 20
MIN_TAG_COUNT = 2
MIN_JUDGE_SCORE = 0.7
AI_RELEVANCE_TERMS = (
    "ai",
    "agent",
    "agents",
    "llm",
    "rag",
    "model",
    "workflow",
    "automation",
    "自动化",
    "智能体",
    "模型",
    "助手",
    "工作流",
    "编码",
)
JUDGE_WEIGHTS = {
    "summary_quality": 0.35,
    "relevance": 0.35,
    "technical_depth": 0.30,
}


POSITIVE_ARTICLE = {
    "id": "github-20260528-001",
    "title": "LangGraph Agent Workflow",
    "source": "github",
    "source_url": "https://github.com/langchain-ai/langgraph",
    "url": "https://github.com/langchain-ai/langgraph",
    "collected_at": "2026-05-28T00:00:00+00:00",
    "summary": "LangGraph 用图结构编排可循环、可持久化的 AI 智能体工作流，适合构建复杂 LLM 应用。",
    "tags": ["agent", "workflow", "llm"],
    "status": "published",
    "score": 0.86,
    "reason": "具备明确的 Agent 工作流价值和工程应用场景。",
    "distribution": {"telegram": False, "feishu": False},
    "metadata": {},
    "updated_at": "2026-05-28T00:00:00+00:00",
}

NEGATIVE_ARTICLE = {
    "id": "notes-20260528-001",
    "title": "Quarterly Office Planning Notes",
    "source": "notes",
    "source_url": "https://example.com/planning-notes",
    "url": "https://example.com/planning-notes",
    "collected_at": "2026-05-28T00:00:00+00:00",
    "summary": "这是一份普通团队会议记录，主要描述办公安排和行政流程。",
    "tags": ["office"],
    "status": "draft",
    "score": 0.92,
    "reason": "内容仅涉及办公室行政安排和团队日程。",
    "distribution": {"telegram": False, "feishu": False},
    "metadata": {},
    "updated_at": "2026-05-28T00:00:00+00:00",
}

BOUNDARY_ARTICLE = {
    "id": "github-20260528-002",
    "title": "Boundary Agent Tool",
    "source": "github",
    "source_url": "https://github.com/example/boundary-agent",
    "url": "https://github.com/example/boundary-agent",
    "collected_at": "2026-05-28T00:00:00+00:00",
    "summary": "AI agent 工具用于测试知识库最小入库边界。",
    "tags": ["ai", "agent"],
    "status": "published",
    "score": MIN_ARTICLE_SCORE,
    "reason": "刚好满足最低分数、摘要长度和标签数量。",
    "distribution": {"telegram": False, "feishu": False},
    "metadata": {},
    "updated_at": "2026-05-28T00:00:00+00:00",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_search_text(article: dict[str, Any]) -> str:
    values = [
        article.get("title", ""),
        article.get("summary", ""),
        article.get("content", ""),
        article.get("reason", ""),
        article.get("score_reason", ""),
        " ".join(str(tag) for tag in article.get("tags", [])),
    ]
    return " ".join(str(value) for value in values).lower()


def _has_ai_relevance_signal(article: dict[str, Any]) -> bool:
    haystack = _as_search_text(article)
    return any(term in haystack for term in AI_RELEVANCE_TERMS)


def _static_eval_failures(article: dict[str, Any]) -> list[str]:
    failures = validate_article_schema(
        article,
        min_summary_chars=MIN_SUMMARY_CHARS,
        min_tags=MIN_TAG_COUNT,
        min_score=MIN_ARTICLE_SCORE,
    )
    if not _has_ai_relevance_signal(article):
        failures.append("ai_relevance")
    return failures


def _normalize_judge_score(value: Any) -> float:
    return normalize_score(value)


def _judge_article_quality(article: dict[str, Any], judge_func: Any) -> float:
    prompt = (
        "请评估这条 AI 知识库候选内容，只返回 JSON。"
        "评分字段为 scores.summary_quality、scores.relevance、scores.technical_depth，"
        "每项使用 0 到 1 分，允许小数。\n"
        f"article: {json.dumps(article, ensure_ascii=False)}"
    )
    payload = judge_func(
        prompt=prompt,
        system="你是严格的 LLM-as-Judge 内容评估器。只返回 JSON。",
        temperature=0.0,
    )
    if isinstance(payload, tuple):
        payload = payload[0]
    scores = payload.get("scores", {}) if isinstance(payload, dict) else {}
    weighted_score = 0.0
    for key, weight in JUDGE_WEIGHTS.items():
        weighted_score += _normalize_judge_score(scores.get(key, 0.0)) * weight
    return round(weighted_score, 3)


def _fake_judge(**kwargs: Any) -> dict[str, Any]:
    prompt = str(kwargs.get("prompt", ""))
    if "Quarterly Office Planning Notes" in prompt:
        return {
            "scores": {
                "summary_quality": 0.4,
                "relevance": 0.1,
                "technical_depth": 0.2,
            }
        }
    if "Boundary Agent Tool" in prompt:
        return {
            "scores": {
                "summary_quality": MIN_JUDGE_SCORE,
                "relevance": MIN_JUDGE_SCORE,
                "technical_depth": MIN_JUDGE_SCORE,
            }
        }
    return {
        "scores": {
            "summary_quality": 0.9,
            "relevance": 0.9,
            "technical_depth": 0.8,
        }
    }


class KnowledgeBaseEvalTests(unittest.TestCase):
    def _load_index_entries(self) -> list[dict[str, Any]]:
        payload = _load_json(INDEX_FILE)
        if isinstance(payload, dict):
            payload = payload.get("items", [])
        self.assertIsInstance(
            payload,
            list,
            "knowledge/articles/index.json must be a list or contain items",
        )
        for entry in payload:
            self.assertIsInstance(entry, dict)
        return payload

    def test_index_is_populated_and_searchable(self) -> None:
        entries = self._load_index_entries()

        self.assertGreaterEqual(len(entries), MIN_INDEXED_ARTICLES)

        seen_urls: set[str] = set()
        seen_files: set[str] = set()
        for entry in entries:
            with self.subTest(file=entry.get("file"), title=entry.get("title")):
                schema_failures = validate_index_entry(entry)
                self.assertFalse(schema_failures, msg=f"index schema failures: {schema_failures}")

                score = normalize_score(entry["score"])
                self.assertGreaterEqual(score, MIN_ARTICLE_SCORE)
                self.assertLessEqual(score, 1.0)
                self.assertIsInstance(entry["tags"], list)
                self.assertGreater(len(entry["tags"]), 0)

                source_url = resolve_source_url(entry)
                self.assertNotIn(source_url, seen_urls)
                self.assertNotIn(entry["file"], seen_files)
                seen_urls.add(source_url)
                seen_files.add(entry["file"])

    def test_indexed_article_files_meet_quality_bar(self) -> None:
        entries = self._load_index_entries()

        for entry in entries:
            article_path = ARTICLES_DIR / str(entry["file"])
            with self.subTest(file=entry["file"]):
                self.assertTrue(article_path.exists())
                article = _load_json(article_path)
                self.assertIsInstance(article, dict)

                schema_failures = validate_article_schema(
                    article,
                    min_summary_chars=MIN_SUMMARY_CHARS,
                    min_tags=MIN_TAG_COUNT,
                    min_score=MIN_ARTICLE_SCORE,
                )
                self.assertFalse(schema_failures, msg=f"article schema failures: {schema_failures}")

                self.assertEqual(article.get("title"), entry.get("title"))
                self.assertEqual(resolve_source_url(article), resolve_source_url(entry))
                self.assertGreaterEqual(len(str(article["summary"]).strip()), MIN_SUMMARY_CHARS)
                self.assertIsInstance(article["tags"], list)
                self.assertGreaterEqual(len(article["tags"]), MIN_TAG_COUNT)

                article_score = normalize_score(article["score"])
                index_score = normalize_score(entry["score"])
                self.assertGreaterEqual(article_score, MIN_ARTICLE_SCORE)
                self.assertAlmostEqual(article_score, index_score, places=2)

                for field in CANONICAL_ARTICLE_FIELDS:
                    self.assertIn(field, article)

    def test_indexed_articles_are_ai_relevant(self) -> None:
        entries = self._load_index_entries()

        for entry in entries:
            article_path = ARTICLES_DIR / str(entry["file"])
            article = _load_json(article_path)
            with self.subTest(file=entry["file"]):
                self.assertTrue(_has_ai_relevance_signal(article))

    def test_minimal_eval_set_covers_positive_negative_and_boundary_cases(self) -> None:
        positive_failures = _static_eval_failures(POSITIVE_ARTICLE)
        negative_failures = _static_eval_failures(NEGATIVE_ARTICLE)
        boundary_failures = _static_eval_failures(BOUNDARY_ARTICLE)

        self.assertFalse(positive_failures)
        self.assertIn("ai_relevance", negative_failures)
        self.assertIn("not_enough_tags", negative_failures)
        self.assertFalse(boundary_failures)

    def test_llm_as_judge_scores_quality_with_thresholds(self) -> None:
        positive_score = _judge_article_quality(POSITIVE_ARTICLE, _fake_judge)
        negative_score = _judge_article_quality(NEGATIVE_ARTICLE, _fake_judge)
        boundary_score = _judge_article_quality(BOUNDARY_ARTICLE, _fake_judge)

        self.assertGreaterEqual(positive_score, MIN_JUDGE_SCORE)
        self.assertLess(negative_score, MIN_JUDGE_SCORE)
        self.assertGreaterEqual(boundary_score, MIN_JUDGE_SCORE)
        self.assertLessEqual(boundary_score, MIN_JUDGE_SCORE)

    def test_human_flags_are_not_index_ready_without_manual_review(self) -> None:
        if not HUMAN_FLAGS_DIR.exists():
            self.skipTest("human_flags directory is missing")

        flag_files = sorted(HUMAN_FLAGS_DIR.glob("*.json"))
        self.assertGreater(len(flag_files), 0, "expected human_flags samples for quality gate")

        for flag_path in flag_files:
            payload = _load_json(flag_path)
            with self.subTest(file=flag_path.name):
                self.assertIn("item", payload)
                item = payload["item"]
                self.assertIsInstance(item, dict)

                review_status = payload.get("review_status", "pending")
                if review_status == "approved":
                    failures = validate_article_schema(
                        item,
                        min_summary_chars=MIN_SUMMARY_CHARS,
                        min_tags=MIN_TAG_COUNT,
                        min_score=MIN_ARTICLE_SCORE,
                    )
                    self.assertFalse(failures, msg=f"approved flag should pass schema: {failures}")
                else:
                    self.assertIn(review_status, {"pending", "rejected"})

    def test_canonical_field_contract_is_documented(self) -> None:
        self.assertIn("source_url", CANONICAL_ARTICLE_FIELDS)
        self.assertIn("collected_at", CANONICAL_ARTICLE_FIELDS)
        self.assertIn("distribution", CANONICAL_ARTICLE_FIELDS)
        self.assertIn("source_url", CANONICAL_INDEX_FIELDS)
        self.assertIn("status", CANONICAL_INDEX_FIELDS)


if __name__ == "__main__":
    unittest.main()
