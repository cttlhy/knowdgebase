from __future__ import annotations

import unittest
from unittest.mock import patch

from model_client import ResponseFormatError
import pipeline as pipeline_module


class PipelineFailureIsolationTests(unittest.TestCase):
    def test_run_pipeline_continues_when_one_item_fails(self) -> None:
        item_ok = {"title": "ok", "url": "https://ok", "source": "github", "date": "2026-01-01", "content": "ok"}
        item_bad = {"title": "bad", "url": "https://bad", "source": "github", "date": "2026-01-01", "content": "bad"}
        analysis_ok = {
            "summary": "good summary",
            "score": 9,
            "tags": ["llm"],
            "highlights": ["h1"],
        }

        with (
            patch.object(pipeline_module, "collect_from_github", return_value=[item_bad, item_ok]),
            patch.object(pipeline_module, "create_provider", return_value=object()),
            patch.object(
                pipeline_module,
                "analyze_item",
                side_effect=[ResponseFormatError("bad format"), analysis_ok],
            ) as analyze_mock,
            patch.object(pipeline_module, "save_outputs") as save_mock,
        ):
            pipeline_module.run_pipeline(sources=["github"], limit=2, dry_run=False)

        self.assertEqual(analyze_mock.call_count, 2)
        self.assertEqual(save_mock.call_count, 1)
        raw_items = save_mock.call_args.kwargs["raw_items"]
        self.assertEqual(len(raw_items), 1)
        self.assertEqual(raw_items[0]["title"], "ok")


if __name__ == "__main__":
    unittest.main()
