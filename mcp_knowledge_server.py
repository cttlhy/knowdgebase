from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

ARTICLES_DIR = Path(__file__).resolve().parent / "knowledge" / "articles"

mcp = FastMCP("local-knowledge-server")


def load_articles() -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    if not ARTICLES_DIR.exists():
        return articles
    for path in sorted(ARTICLES_DIR.glob("*.json")):
        try:
            article = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(article, dict):
            if "id" not in article:
                article["id"] = path.stem
            articles.append(article)
    return articles


ARTICLES = load_articles()
ARTICLE_BY_ID = {article["id"]: article for article in ARTICLES}


@mcp.tool()
def search_articles(keyword: str, limit: int = 5) -> str:
    """按关键词搜索文章标题和摘要。"""
    keyword = str(keyword).strip().casefold()
    limit = max(1, min(int(limit), 50))
    if not keyword:
        return json.dumps([], ensure_ascii=False)

    results: list[dict[str, Any]] = []
    for article in ARTICLES:
        title = str(article.get("title", ""))
        summary = str(article.get("summary", ""))
        if keyword not in f"{title}\n{summary}".casefold():
            continue
        results.append(
            {
                "id": article.get("id", ""),
                "title": title,
                "source": article.get("source", ""),
                "summary": summary,
                "score": article.get("score"),
                "tags": article.get("tags", []),
            }
        )
        if len(results) >= limit:
            break
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def get_article(article_id: str) -> str:
    """按 ID 获取文章完整内容。"""
    article = ARTICLE_BY_ID.get(str(article_id))
    if article is None:
        return json.dumps(
            {"error": f"article not found: {article_id}"}, ensure_ascii=False
        )
    return json.dumps(article, ensure_ascii=False, indent=2)


@mcp.tool()
def knowledge_stats() -> str:
    """返回文章总数、来源分布和热门标签。"""
    sources: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    for article in ARTICLES:
        sources[str(article.get("source") or "unknown")] += 1
        article_tags = article.get("tags", [])
        if isinstance(article_tags, list):
            tags.update(tag for tag in article_tags if isinstance(tag, str))
    return json.dumps(
        {
            "total_articles": len(ARTICLES),
            "sources": dict(sources.most_common()),
            "top_tags": dict(tags.most_common(20)),
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
