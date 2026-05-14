from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from patterns import router


class RouterTests(unittest.TestCase):
    def test_route_uses_keyword_for_github_without_llm(self) -> None:
        with patch.object(router, "handle_github_search", return_value="ok") as github_mock:
            with patch.object(router, "chat_json") as chat_json_mock:
                result = router.route("帮我搜索 github 上的多智能体框架")

        self.assertEqual(result, "ok")
        github_mock.assert_called_once()
        chat_json_mock.assert_not_called()

    def test_route_uses_llm_fallback_for_ambiguous_query(self) -> None:
        with patch.object(router, "chat_json", return_value=({"intent": "knowledge_query"}, {"total": 1})):
            with patch.object(router, "handle_knowledge_query", return_value="knowledge") as handler_mock:
                result = router.route("你觉得这个项目怎么样")

        self.assertEqual(result, "knowledge")
        handler_mock.assert_called_once()

    def test_handle_github_search_encodes_query_with_quote(self) -> None:
        captured: dict[str, str] = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

            def read(self) -> bytes:
                payload = {
                    "items": [
                        {
                            "full_name": "example/repo",
                            "html_url": "https://github.com/example/repo",
                            "description": "demo",
                            "stargazers_count": 100,
                        }
                    ]
                }
                return json.dumps(payload).encode("utf-8")

        def _fake_urlopen(request_obj, timeout=10):
            captured["url"] = request_obj.full_url
            return _FakeResponse()

        with patch.object(router.urllib.request, "urlopen", side_effect=_fake_urlopen):
            output = router.handle_github_search("中文 空格")

        self.assertIn("%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC", captured["url"])
        self.assertIn("example/repo", output)
        self.assertIn("Stars: 100", output)

    def test_handle_knowledge_query_reads_local_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "index.json"
            tmp_path.write_text(
                json.dumps(
                    [
                        {
                            "title": "OpenAI Router Design",
                            "summary": "Router pattern example.",
                            "source_url": "https://example.com/router",
                            "tags": ["router", "agent"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(router, "INDEX_FILE", tmp_path):
                output = router.handle_knowledge_query("router")

        self.assertIn("OpenAI Router Design", output)

    def test_handle_knowledge_query_fallback_to_article_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            articles_dir = Path(tmp_dir)
            (articles_dir / "a.json").write_text(
                json.dumps(
                    {
                        "title": "RAG 入门",
                        "summary": "介绍向量检索与生成。",
                        "source_url": "https://example.com/rag",
                        "tags": ["rag", "llm"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (articles_dir / "b.json").write_text(
                json.dumps(
                    {
                        "title": "Agent 设计",
                        "summary": "关于多智能体。",
                        "tags": ["agent"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            missing_index = articles_dir / "index.json"
            with patch.object(router, "INDEX_FILE", missing_index):
                output = router.handle_knowledge_query("rag")

        self.assertIn("RAG 入门", output)

    def test_handle_github_search_retries_with_ascii_keywords_when_no_results(self) -> None:
        captured_urls: list[str] = []

        class _FakeResponse:
            def __init__(self, payload: dict):
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

        responses = [
            {"items": []},
            {
                "items": [
                    {
                        "full_name": "example/ai-agent-framework",
                        "html_url": "https://github.com/example/ai-agent-framework",
                        "description": "AI agent framework",
                        "stargazers_count": 42,
                    }
                ]
            },
        ]

        def _fake_urlopen(request_obj, timeout=10):
            captured_urls.append(request_obj.full_url)
            payload = responses[len(captured_urls) - 1]
            return _FakeResponse(payload)

        with patch.object(router.urllib.request, "urlopen", side_effect=_fake_urlopen):
            output = router.handle_github_search("搜索最近的 AI Agent 框架")

        self.assertEqual(len(captured_urls), 2)
        self.assertIn("AI%20Agent", captured_urls[1])
        self.assertIn("example/ai-agent-framework", output)


if __name__ == "__main__":
    unittest.main()
