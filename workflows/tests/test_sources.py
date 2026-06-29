from __future__ import annotations

import sys
import types
import unittest
import urllib.error
from unittest.mock import patch


_model_client = types.ModuleType("pipeline.model_client")
_model_client.Usage = lambda **_: None
_model_client.chat_json = lambda **_: ({}, None)
sys.modules.setdefault("pipeline.model_client", _model_client)

import workflows.sources as sources_module


class MultiSourceCollectTests(unittest.TestCase):
    def test_collect_from_github_maps_repository_fields(self) -> None:
        payload = {
            "items": [
                {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                    "description": "AI agent repo",
                    "language": "Python",
                    "stargazers_count": 42,
                }
            ]
        }
        with patch.object(sources_module.urllib.request, "urlopen") as urlopen_mock:
            response = urlopen_mock.return_value.__enter__.return_value
            response.read.return_value = __import__("json").dumps(payload).encode("utf-8")
            items, error = sources_module.collect_from_github(limit=1)

        self.assertIsNone(error)
        self.assertEqual(items[0]["url"], "https://github.com/owner/repo")
        self.assertEqual(items[0]["source"], "github")

    def test_collect_from_sources_merges_github_and_rss(self) -> None:
        github_items = [{"title": "gh", "url": "https://github.com/a/b", "source": "github"}]
        rss_items = [{"title": "rss", "url": "https://example.com/a", "source": "rss"}]
        with patch.object(sources_module, "collect_from_github", return_value=(github_items, None)):
            with patch.object(sources_module, "collect_from_rss", return_value=(rss_items, None)):
                items, errors = sources_module.collect_from_sources(sources=["github", "rss"], limit=4)

        self.assertEqual(errors, [])
        self.assertEqual(len(items), 2)
        self.assertEqual({item["source"] for item in items}, {"github", "rss"})

    def test_collect_from_github_returns_error_on_network_failure(self) -> None:
        with patch.object(
            sources_module.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("network down"),
        ):
            items, error = sources_module.collect_from_github(limit=1)

        self.assertEqual(items, [])
        self.assertIn("network down", error or "")


if __name__ == "__main__":
    unittest.main()
