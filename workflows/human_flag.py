from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from workflows.state import KBState

LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(text: Any) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(text or "")).strip("-").lower()
    return slug[:80] or "human-review"


def human_flag_node(state: KBState) -> dict[str, Any]:
    """Persist failed analysis items for manual review outside the main knowledge base."""
    LOGGER.info("[human_flag_node] Flagging items for manual review")
    items = state.get("analyses") or state.get("analyzed_items") or state.get("articles") or []
    repo_root = Path(str(state.get("knowledge_root") or Path(__file__).resolve().parent.parent))
    flag_dir = repo_root / "human_flags"
    flag_dir.mkdir(parents=True, exist_ok=True)

    now = _now_iso()
    date_stamp = datetime.now(UTC).strftime("%Y%m%d")
    saved_files: list[str] = []
    feedback = str(state.get("review_feedback") or state.get("feedback") or "").strip()
    review = state.get("review") or {}
    iteration = int(state.get("iteration", 0))
    max_iterations = int(state.get("max_iterations", 0))

    for index, item in enumerate(items, start=1):
        unique_source = str(item.get("url") or item.get("title") or f"item-{index}")
        unique_suffix = sha1(f"{unique_source}:{index}:{now}".encode("utf-8")).hexdigest()[:10]
        filename = f"{date_stamp}-{_slugify(item.get('title') or unique_source)}-{unique_suffix}.json"
        payload = {
            "flagged_at": now,
            "review_status": "pending",
            "reason": "max_iterations_exceeded",
            "iteration": iteration,
            "max_iterations": max_iterations,
            "review_feedback": feedback,
            "review": review,
            "item": item,
        }
        target = flag_dir / filename
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_files.append(target.name)

    return {
        "review_passed": False,
        "human_flagged": True,
        "human_flagged_count": len(saved_files),
        "human_flagged_files": saved_files,
        "human_flag_dir": str(flag_dir),
    }
