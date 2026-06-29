from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False


_model_client = types.ModuleType("pipeline.model_client")
_model_client.Usage = _Usage
_model_client.chat = lambda **_: ("", _Usage())
_model_client.chat_json = lambda **_: ({}, _Usage())
sys.modules.setdefault("pipeline.model_client", _model_client)

import workflows.human_review as human_review_module


class HumanReviewTests(unittest.TestCase):
    def test_approve_human_flag_promotes_item_and_marks_flag_approved(self) -> None:
        item = {
            "title": "Needs Human Review",
            "url": "https://github.com/example/review-me",
            "source": "github",
            "summary": "AI agent 工具在人工复核后应能回流到正式知识库。",
            "tags": ["ai", "agent"],
            "score": 0.78,
            "reason": "人工确认后入库。",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flag_dir = root / "human_flags"
            flag_dir.mkdir(parents=True)
            flag_path = flag_dir / "20260528-review-me-abc.json"
            flag_path.write_text(
                json.dumps(
                    {
                        "flagged_at": "2026-05-28T00:00:00+00:00",
                        "review_status": "pending",
                        "item": item,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = human_review_module.approve_human_flag(
                flag_path,
                knowledge_root=root,
                reviewer_note="人工确认通过",
            )

            self.assertEqual(result["saved_count"], 1)
            payload = json.loads(flag_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["review_status"], "approved")
            self.assertEqual(payload["reviewer_note"], "人工确认通过")

            articles_dir = root / "knowledge" / "articles"
            article_files = [path for path in articles_dir.glob("*.json") if path.name != "index.json"]
            self.assertEqual(len(article_files), 1)
            saved = json.loads(article_files[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["source_url"], "https://github.com/example/review-me")
            self.assertEqual(saved["status"], "published")

    def test_reject_human_flag_marks_status_without_saving_article(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flag_dir = root / "human_flags"
            flag_dir.mkdir(parents=True)
            flag_path = flag_dir / "20260528-reject-me-abc.json"
            flag_path.write_text(
                json.dumps(
                    {
                        "review_status": "pending",
                        "item": {"title": "Reject Me", "url": "https://example.com/reject"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            human_review_module.reject_human_flag(flag_path, reviewer_note="不符合入库标准")

            payload = json.loads(flag_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["review_status"], "rejected")
            self.assertFalse((root / "knowledge" / "articles").exists())


if __name__ == "__main__":
    unittest.main()
