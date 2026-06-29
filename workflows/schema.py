from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from workflows._utils import coerce_bool, safe_float

DEFAULT_DISTRIBUTION = {"telegram": False, "feishu": False}
VALID_STATUSES = frozenset({"draft", "review", "published", "archived"})
CANONICAL_ARTICLE_FIELDS = (
    "id",
    "title",
    "source",
    "source_url",
    "collected_at",
    "summary",
    "tags",
    "status",
    "score",
    "reason",
    "distribution",
    "metadata",
    "updated_at",
)
CANONICAL_INDEX_FIELDS = (
    "id",
    "title",
    "source",
    "source_url",
    "url",
    "score",
    "tags",
    "status",
    "file",
    "updated_at",
)
DEFAULT_STATUS = "published"
VALID_STATUSES = frozenset({"raw", "analyzed", "draft", "published", "archived"})

REQUIRED_ARTICLE_FIELDS = (
    "id",
    "title",
    "source",
    "source_url",
    "collected_at",
    "summary",
    "tags",
    "status",
    "score",
    "reason",
    "distribution",
)
REQUIRED_INDEX_FIELDS = (
    "id",
    "title",
    "source",
    "source_url",
    "score",
    "tags",
    "status",
    "file",
)


def normalize_score(raw_score: Any) -> float:
    """Normalize legacy 1-10 scores and canonical 0-1 scores to 0-1."""
    score = safe_float(raw_score, default=0.0)
    if 1.0 < score <= 10.0:
        score = score / 10.0
    return round(max(0.0, min(1.0, score)), 4)


def build_entry_id(source: Any, collected_at: Any, index: int) -> str:
    """Build stable ids that match hooks/validate_json.py."""
    safe_source = re.sub(r"[^a-z0-9-]+", "-", str(source or "unknown").strip().lower()).strip("-")
    safe_source = re.sub(r"-{2,}", "-", safe_source) or "unknown"
    return f"{safe_source}-{_compact_date(collected_at)}-{index:03d}"


def canonicalize_article(
    article: dict[str, Any],
    *,
    index: int,
    now: str | None = None,
    default_status: str = "published",
) -> dict[str, Any]:
    """Return the canonical knowledge article shape used by workflow saves."""
    timestamp = now or datetime.now(UTC).isoformat()
    source_url = str(article.get("source_url") or article.get("url") or "").strip()
    collected_at = str(article.get("collected_at") or article.get("date") or timestamp).strip()
    source = str(article.get("source") or "unknown").strip().lower() or "unknown"
    article_id = str(article.get("id") or build_entry_id(source, collected_at, index)).strip()

    distribution = {**DEFAULT_DISTRIBUTION}
    existing_distribution = article.get("distribution")
    if isinstance(existing_distribution, dict):
        for channel in distribution:
            distribution[channel] = coerce_bool(existing_distribution.get(channel), default=False)

    metadata = dict(article.get("metadata") or {})
    for source_field in ("language", "popularity", "source_name"):
        if source_field in article and article[source_field] not in (None, ""):
            metadata.setdefault(source_field, article[source_field])

    payload = {
        **article,
        "id": article_id,
        "title": str(article.get("title") or "").strip(),
        "source": source,
        "source_url": source_url,
        # Keep `url` while existing MCP/router consumers migrate to source_url.
        "url": source_url,
        "collected_at": collected_at,
        "summary": str(article.get("summary") or "").strip(),
        "tags": [str(tag).strip() for tag in article.get("tags", []) if str(tag).strip()],
        "status": str(article.get("status") or default_status).strip() or default_status,
        "score": normalize_score(article.get("score")),
        "reason": str(article.get("reason") or article.get("score_reason") or "").strip(),
        "distribution": distribution,
        "metadata": metadata,
        "updated_at": timestamp,
    }
    return payload


def build_index_entry(article: dict[str, Any], *, filename: str, now: str) -> dict[str, Any]:
    """Create the searchable index projection for a canonical article."""
    source_url = str(article.get("source_url") or article.get("url") or "").strip()
    return {
        "id": article.get("id", ""),
        "title": article.get("title", ""),
        "source": article.get("source", ""),
        "source_url": source_url,
        "url": source_url,
        "score": normalize_score(article.get("score")),
        "tags": article.get("tags", []),
        "status": article.get("status", "published"),
        "file": filename,
        "updated_at": now,
    }


def _compact_date(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) >= 8:
        return digits[:8]
    return datetime.now(UTC).strftime("%Y%m%d")


def resolve_source_url(article: dict[str, Any]) -> str:
    """Return canonical source URL, falling back to legacy `url` field."""
    return str(article.get("source_url") or article.get("url") or "").strip()


def validate_article_schema(
    article: dict[str, Any],
    *,
    min_summary_chars: int = 20,
    min_tags: int = 2,
    min_score: float = 0.0,
    max_score: float = 1.0,
) -> list[str]:
    """Return validation failures for a canonical article payload."""
    failures: list[str] = []
    for field in CANONICAL_ARTICLE_FIELDS:
        if field not in article or article[field] in (None, ""):
            failures.append(f"missing_{field}")

    source_url = resolve_source_url(article)
    if not source_url.startswith(("http://", "https://")):
        failures.append("invalid_source_url")

    summary = str(article.get("summary") or "").strip()
    if len(summary) < min_summary_chars:
        failures.append("summary_too_short")

    tags = article.get("tags")
    if not isinstance(tags, list) or len(tags) < min_tags:
        failures.append("not_enough_tags")

    score = normalize_score(article.get("score"))
    if score < min_score or score > max_score:
        failures.append("score_out_of_range")

    status = str(article.get("status") or "")
    if status not in VALID_STATUSES:
        failures.append("invalid_status")

    distribution = article.get("distribution")
    if not isinstance(distribution, dict):
        failures.append("invalid_distribution")
    elif not all(channel in distribution for channel in DEFAULT_DISTRIBUTION):
        failures.append("incomplete_distribution")

    metadata = article.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        failures.append("invalid_metadata")

    return failures


def validate_index_entry(entry: dict[str, Any]) -> list[str]:
    """Return validation failures for an index projection entry."""
    failures: list[str] = []
    for field in CANONICAL_INDEX_FIELDS:
        if field not in entry or entry[field] in (None, ""):
            failures.append(f"missing_{field}")

    source_url = resolve_source_url(entry)
    if not source_url.startswith(("http://", "https://")):
        failures.append("invalid_source_url")

    tags = entry.get("tags")
    if not isinstance(tags, list) or not tags:
        failures.append("empty_tags")

    status = str(entry.get("status") or "")
    if status not in VALID_STATUSES:
        failures.append("invalid_status")

    return failures
