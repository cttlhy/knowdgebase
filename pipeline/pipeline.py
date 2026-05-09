from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from model_client import chat_with_retry, create_provider

LOGGER = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "knowledge" / "raw"
ARTICLES_DIR = ROOT_DIR / "knowledge" / "articles"
RSS_CONFIG = Path(__file__).resolve().parent / "rss_sources.yaml"
SUPPORTED_SOURCES = {"github", "rss"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="四步知识库自动化流水线")
    parser.add_argument("--sources", default="github,rss", help="数据源: github,rss")
    parser.add_argument("--limit", type=int, default=20, help="总采集数量上限")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式，不写文件")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    return parser.parse_args()


def parse_sources(raw_sources: str) -> list[str]:
    sources = [item.strip().lower() for item in raw_sources.split(",") if item.strip()]
    if not sources:
        raise ValueError("`--sources` 不能为空")
    invalid = [src for src in sources if src not in SUPPORTED_SOURCES]
    if invalid:
        raise ValueError(f"不支持的数据源: {', '.join(invalid)}")
    return sources


def slugify(text: str) -> str:
    simple = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text).strip("-").lower()
    return simple[:80] or "article"


def utc_today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def utc_date_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def collect_from_github(limit: int) -> list[dict[str, Any]]:
    url = "https://api.github.com/search/repositories"
    params = {"q": "ai OR llm OR agent", "sort": "stars", "order": "desc", "per_page": min(limit, 100)}
    headers = {"Accept": "application/vnd.github+json"}
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    items = data.get("items", [])
    collected: list[dict[str, Any]] = []
    for item in items[:limit]:
        collected.append(
            {
                "title": item.get("full_name", ""),
                "url": item.get("html_url", ""),
                "source": "github",
                "date": utc_today_iso(),
                "popularity": f"stars:{item.get('stargazers_count', 0)}",
                "content": item.get("description") or "",
            }
        )
    return collected


def load_enabled_rss_sources() -> list[dict[str, str]]:
    text = RSS_CONFIG.read_text(encoding="utf-8")
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


def parse_rss_items(feed: str, source_name: str) -> list[dict[str, Any]]:
    item_blocks = re.findall(r"<item\b.*?>.*?</item>", feed, flags=re.DOTALL | re.IGNORECASE)
    collected: list[dict[str, Any]] = []
    for block in item_blocks:
        title = extract_xml_tag(block, "title")
        url = extract_xml_tag(block, "link")
        description = extract_xml_tag(block, "description")
        pub_date = extract_xml_tag(block, "pubDate")
        if not title or not url:
            continue
        collected.append(
            {
                "title": clean_html(title),
                "url": clean_html(url),
                "source": "rss",
                "source_name": source_name,
                "date": clean_html(pub_date) or utc_today_iso(),
                "popularity": "",
                "content": clean_html(description),
            }
        )
    return collected


def extract_xml_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def clean_html(text: str) -> str:
    no_cdata = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    no_tags = re.sub(r"<[^>]+>", " ", no_cdata)
    compact = re.sub(r"\s+", " ", no_tags).strip()
    return compact


def collect_from_rss(limit: int) -> list[dict[str, Any]]:
    all_sources = load_enabled_rss_sources()
    if not all_sources:
        return []
    per_source = max(1, limit // len(all_sources))
    collected: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for source in all_sources:
            try:
                response = client.get(source["url"])
                response.raise_for_status()
                feed_items = parse_rss_items(response.text, source["name"])
                collected.extend(feed_items[:per_source])
            except httpx.HTTPError as exc:
                LOGGER.warning("RSS 源抓取失败，已跳过: %s (%s)", source["name"], exc)
    return collected[:limit]


def analyze_item(item: dict[str, Any], provider: Any) -> dict[str, Any]:
    # 这里让模型只输出 JSON，减少后处理复杂度。
    prompt = (
        "你是知识库分析助手。请基于输入内容输出严格 JSON，字段为"
        'summary(string), score(int 1-10), tags(array of string), highlights(array of string)。'
        f"\n标题: {item.get('title', '')}\n链接: {item.get('url', '')}\n内容: {item.get('content', '')[:2000]}"
    )
    messages = [
        {"role": "system", "content": "请只返回 JSON，不要加解释。"},
        {"role": "user", "content": prompt},
    ]
    response = chat_with_retry(provider=provider, messages=messages, temperature=0.2)
    parsed = safe_parse_json(response.content)
    return {
        "summary": str(parsed.get("summary") or "")[:500],
        "score": int(parsed.get("score") or 0),
        "tags": [str(x) for x in (parsed.get("tags") or []) if str(x).strip()][:8],
        "highlights": [str(x) for x in (parsed.get("highlights") or []) if str(x).strip()][:5],
    }


def safe_parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        matched = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not matched:
            return {}
        try:
            return json.loads(matched.group(0))
        except json.JSONDecodeError:
            return {}


def organize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("url") or item.get("title")).strip().lower()
        if key:
            deduped[key] = item
    normalized: list[dict[str, Any]] = []
    for item in deduped.values():
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        summary = str(item.get("summary", "")).strip()
        if not title or not url or not summary:
            continue
        normalized.append(
            {
                "title": title,
                "url": url,
                "source": str(item.get("source", "unknown")),
                "date": str(item.get("date", utc_today_iso())),
                "popularity": str(item.get("popularity", "")),
                "summary": summary,
                "highlights": item.get("highlights") or [],
                "score": int(item.get("score") or 0),
                "tags": item.get("tags") or [],
            }
        )
    return normalized


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_outputs(raw_items: list[dict[str, Any]], articles: list[dict[str, Any]], dry_run: bool) -> None:
    today = utc_date_compact()
    if dry_run:
        LOGGER.info("[dry-run] 跳过落盘。raw=%s, articles=%s", len(raw_items), len(articles))
        return
    raw_path = RAW_DIR / f"collected-{today}.json"
    write_json(raw_path, raw_items)
    for article in articles:
        name = f"{today}-{article['source']}-{slugify(article['title'])}.json"
        write_json(ARTICLES_DIR / name, article)
    LOGGER.info("已保存 raw=%s, articles=%s", raw_path, len(articles))


def run_pipeline(sources: list[str], limit: int, dry_run: bool) -> None:
    collected: list[dict[str, Any]] = []
    per_source_limit = max(1, limit // len(sources))
    if "github" in sources:
        try:
            github_items = collect_from_github(per_source_limit)
            collected.extend(github_items)
            LOGGER.info("GitHub 采集完成: %s", len(github_items))
        except httpx.HTTPError as exc:
            LOGGER.warning("GitHub 采集失败，已跳过: %s", exc)
    if "rss" in sources:
        try:
            rss_items = collect_from_rss(per_source_limit)
            collected.extend(rss_items)
            LOGGER.info("RSS 采集完成: %s", len(rss_items))
        except httpx.HTTPError as exc:
            LOGGER.warning("RSS 采集失败，已跳过: %s", exc)
    if not collected:
        LOGGER.warning("无可分析内容，流水线结束。")
        return

    provider = create_provider()
    analyzed: list[dict[str, Any]] = []
    for item in collected:
        analysis = analyze_item(item, provider)
        analyzed.append({**item, **analysis})
    organized = organize_items(analyzed)
    save_outputs(raw_items=analyzed, articles=organized, dry_run=dry_run)
    LOGGER.info("流水线完成。collect=%s analyze=%s organize=%s save=%s", len(collected), len(analyzed), len(organized), len(organized))


def main() -> None:
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    sources = parse_sources(args.sources)
    limit = max(1, args.limit)
    run_pipeline(sources=sources, limit=limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
