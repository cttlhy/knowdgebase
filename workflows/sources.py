from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
GITHUB_SEARCH_API = "https://api.github.com/search/repositories"
DEFAULT_RSS_CONFIG = Path(__file__).resolve().parent.parent / "pipeline" / "rss_sources.yaml"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def collect_from_github(
    *,
    limit: int,
    query: str = "ai OR llm OR agent",
    token: str = "",
) -> tuple[list[dict[str, Any]], str | None]:
    """Collect AI-related repositories from GitHub Search API."""
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
    )
    headers = {"Accept": "application/vnd.github+json"}
    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    request = urllib.request.Request(
        url=f"{GITHUB_SEARCH_API}?{params}",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        message = f"github collect failed: {exc}"
        LOGGER.warning("[collect_from_github] %s", message)
        return [], message

    collected: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        collected.append(
            {
                "title": item.get("full_name") or "",
                "url": item.get("html_url") or "",
                "source": "github",
                "date": _now_iso(),
                "content": item.get("description") or "",
                "language": item.get("language") or "",
                "popularity": f"stars:{item.get('stargazers_count', 0)}",
            }
        )
    return collected, None


def load_enabled_rss_sources(config_path: Path | None = None) -> list[dict[str, str]]:
    """Load enabled RSS sources from pipeline/rss_sources.yaml."""
    path = config_path or DEFAULT_RSS_CONFIG
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"-\s+name:.*?(?=\n\s*-\s+name:|\Z)", text, flags=re.DOTALL)
    sources: list[dict[str, str]] = []
    for block in blocks:
        if not re.search(r"enabled:\s*true", block):
            continue
        name_match = re.search(r"name:\s*(.+)", block)
        url_match = re.search(r"url:\s*(.+)", block)
        if not name_match or not url_match:
            continue
        sources.append({"name": name_match.group(1).strip(), "url": url_match.group(1).strip()})
    return sources


def _extract_xml_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _clean_html(text: str) -> str:
    no_cdata = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    no_tags = re.sub(r"<[^>]+>", " ", no_cdata)
    return re.sub(r"\s+", " ", no_tags).strip()


def _parse_rss_items(feed: str, source_name: str) -> list[dict[str, Any]]:
    item_blocks = re.findall(r"<item\b.*?>.*?</item>", feed, flags=re.DOTALL | re.IGNORECASE)
    collected: list[dict[str, Any]] = []
    for block in item_blocks:
        title = _extract_xml_tag(block, "title")
        url = _extract_xml_tag(block, "link")
        description = _extract_xml_tag(block, "description")
        pub_date = _extract_xml_tag(block, "pubDate")
        if not title or not url:
            continue
        collected.append(
            {
                "title": _clean_html(title),
                "url": _clean_html(url),
                "source": "rss",
                "source_name": source_name,
                "date": _clean_html(pub_date) or _now_iso(),
                "content": _clean_html(description),
            }
        )
    return collected


def collect_from_rss(
    *,
    limit: int,
    config_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Collect items from enabled RSS feeds."""
    all_sources = load_enabled_rss_sources(config_path)
    if not all_sources:
        return [], None

    per_source = max(1, limit // len(all_sources))
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for source in all_sources:
        request = urllib.request.Request(
            url=source["url"],
            headers={"User-Agent": "knowdeage-kb/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                feed = response.read().decode("utf-8", errors="replace")
            collected.extend(_parse_rss_items(feed, source["name"])[:per_source])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source['name']}: {exc}")
            LOGGER.warning("[collect_from_rss] skipped %s: %s", source["name"], exc)

    if errors and not collected:
        return [], f"rss collect failed: {'; '.join(errors)}"
    return collected[:limit], None


def collect_from_sources(
    *,
    sources: list[str],
    limit: int,
    github_query: str = "ai OR llm OR agent",
    github_token: str = "",
    rss_config_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect from multiple sources and merge results."""
    normalized = [source.strip().lower() for source in sources if source.strip()]
    if not normalized:
        normalized = ["github"]

    per_source = max(1, limit // len(normalized))
    collected: list[dict[str, Any]] = []
    errors: list[str] = []

    if "github" in normalized:
        items, error = collect_from_github(limit=per_source, query=github_query, token=github_token)
        collected.extend(items)
        if error:
            errors.append(error)

    if "rss" in normalized:
        items, error = collect_from_rss(limit=per_source, config_path=rss_config_path)
        collected.extend(items)
        if error:
            errors.append(error)

    return collected[:limit], errors
