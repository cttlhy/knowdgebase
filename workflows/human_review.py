from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from workflows.nodes import save_node
from workflows.schema import canonicalize_article, resolve_source_url
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_human_flag(path: Path) -> dict[str, Any]:
    """Load a human flag JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: root must be an object")
    return payload


def list_pending_flags(flag_dir: Path) -> list[Path]:
    """Return human flag files that are still pending review."""
    if not flag_dir.exists():
        return []
    pending: list[Path] = []
    for path in sorted(flag_dir.glob("*.json")):
        try:
            payload = load_human_flag(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if payload.get("review_status", REVIEW_STATUS_PENDING) == REVIEW_STATUS_PENDING:
            pending.append(path)
    return pending


def approve_human_flag(
    flag_path: Path,
    *,
    knowledge_root: Path | str,
    reviewer_note: str = "",
    now: str | None = None,
) -> dict[str, Any]:
    """Promote an approved human flag item into the knowledge base."""
    payload = load_human_flag(flag_path)
    if payload.get("review_status") == REVIEW_STATUS_APPROVED:
        raise ValueError(f"{flag_path.name} is already approved")

    item = payload.get("item")
    if not isinstance(item, dict):
        raise ValueError(f"{flag_path.name} is missing a valid item object")

    timestamp = now or _now_iso()
    article = canonicalize_article(item, index=1, now=timestamp, default_status="published")
    if reviewer_note.strip():
        metadata = dict(article.get("metadata") or {})
        metadata["human_review_note"] = reviewer_note.strip()
        article["metadata"] = metadata

    save_result = save_node({"articles": [article], "knowledge_root": str(knowledge_root)})

    payload["review_status"] = REVIEW_STATUS_APPROVED
    payload["approved_at"] = timestamp
    payload["approved_article_id"] = article["id"]
    payload["approved_source_url"] = resolve_source_url(article)
    if reviewer_note.strip():
        payload["reviewer_note"] = reviewer_note.strip()
    flag_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    LOGGER.info("[approve_human_flag] promoted %s -> %s", flag_path.name, article["id"])
    return {
        "flag_file": flag_path.name,
        "article_id": article["id"],
        "source_url": resolve_source_url(article),
        **save_result,
    }


def reject_human_flag(
    flag_path: Path,
    *,
    reviewer_note: str = "",
    now: str | None = None,
) -> dict[str, Any]:
    """Mark a human flag as rejected without promoting it."""
    payload = load_human_flag(flag_path)
    timestamp = now or _now_iso()
    payload["review_status"] = REVIEW_STATUS_REJECTED
    payload["rejected_at"] = timestamp
    if reviewer_note.strip():
        payload["reviewer_note"] = reviewer_note.strip()
    flag_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("[reject_human_flag] rejected %s", flag_path.name)
    return {"flag_file": flag_path.name, "review_status": REVIEW_STATUS_REJECTED}


def promote_pending_flags(
    state: KBState,
    *,
    reviewer_note: str = "",
) -> dict[str, Any]:
    """LangGraph-compatible node that promotes all pending approved flags."""
    repo_root = Path(str(state.get("knowledge_root") or Path(__file__).resolve().parent.parent))
    flag_dir = repo_root / "human_flags"
    only_files = state.get("human_flag_files") or []
    pending = list_pending_flags(flag_dir)
    if only_files:
        allowed = {str(name) for name in only_files}
        pending = [path for path in pending if path.name in allowed]

    promoted: list[dict[str, Any]] = []
    for path in pending:
        if state.get("auto_approve_human_flags", True):
            promoted.append(
                approve_human_flag(
                    path,
                    knowledge_root=repo_root,
                    reviewer_note=reviewer_note,
                )
            )
    return {
        "human_review_promoted_count": len(promoted),
        "human_review_promoted": promoted,
    }


def _build_cli() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(description="Promote or reject human-flagged knowledge items.")
    parser.add_argument("action", choices=["approve", "reject", "list"])
    parser.add_argument("--flag-file", help="Specific human flag filename to process")
    parser.add_argument("--knowledge-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--note", default="", help="Reviewer note")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)
    root = Path(args.knowledge_root)
    flag_dir = root / "human_flags"

    if args.action == "list":
        pending = list_pending_flags(flag_dir)
        for path in pending:
            print(path.name)
        return 0

    if not args.flag_file:
        parser.error("--flag-file is required for approve/reject")

    flag_path = flag_dir / args.flag_file
    if args.action == "approve":
        result = approve_human_flag(flag_path, knowledge_root=root, reviewer_note=args.note)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = reject_human_flag(flag_path, reviewer_note=args.note)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
