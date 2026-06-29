#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.distribution import distribute_node
from workflows.env_loader import apply_env_file
from workflows.feishu_app import feishu_app_is_configured, resolve_feishu_app_config
from workflows.schema import canonicalize_article, normalize_score, resolve_source_url

LOGGER = logging.getLogger(__name__)


def _today_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _load_article(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name}: root must be an object")
    return payload


def _already_sent_to_feishu(article: dict[str, Any]) -> bool:
    distribution = article.get("distribution")
    return isinstance(distribution, dict) and bool(distribution.get("feishu"))


def collect_daily_articles(
    articles_dir: Path,
    *,
    date_stamp: str,
    limit: int,
    send_all: bool,
    only_new: bool,
) -> list[dict[str, Any]]:
    pattern = f"{date_stamp}-*.json"
    candidates: list[tuple[float, dict[str, Any]]] = []
    for path in sorted(articles_dir.glob(pattern)):
        if path.name == "index.json":
            continue
        article = _load_article(path)
        if only_new and _already_sent_to_feishu(article):
            continue
        if not str(article.get("summary") or "").strip():
            continue
        if not resolve_source_url(article):
            continue
        score = normalize_score(article.get("score"))
        canonical = canonicalize_article(article, index=1)
        canonical["_file"] = path.name
        candidates.append((score, canonical))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = candidates if send_all else candidates[:limit]
    return [article for _, article in selected]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Distribute today's collected articles to Feishu/Telegram.")
    parser.add_argument("--env-file", default=str(ROOT_DIR / ".env"))
    parser.add_argument("--date", default="", help="Article date stamp YYYYMMDD (default: today UTC)")
    parser.add_argument("--limit", type=int, default=5, help="Max articles to send when --all is not set")
    parser.add_argument("--all", action="store_true", help="Send all matching articles instead of top-N by score")
    parser.add_argument("--include-sent", action="store_true", help="Include articles already marked distribution.feishu=true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    apply_env_file(Path(args.env_file))

    feishu = resolve_feishu_app_config({})
    if not feishu_app_is_configured(feishu):
        LOGGER.error("Feishu app is not fully configured (need APP_ID, APP_SECRET, RECEIVE_ID).")
        return 1

    date_stamp = args.date.strip() or _today_compact()
    articles_dir = ROOT_DIR / "knowledge" / "articles"
    articles = collect_daily_articles(
        articles_dir,
        date_stamp=date_stamp,
        limit=max(1, args.limit),
        send_all=args.all,
        only_new=not args.include_sent,
    )
    if not articles:
        LOGGER.info("No articles to distribute for date=%s", date_stamp)
        return 0

    for article in articles:
        article.pop("_file", None)

    update = distribute_node(
        {
            "articles": articles,
            "knowledge_root": str(ROOT_DIR),
            "distribution_dry_run": args.dry_run,
            **feishu,
        }
    )
    results = update.get("distribution_results") or []
    sent = sum(1 for item in results if item.get("feishu"))
    LOGGER.info(
        "Distribution finished for %s: candidates=%s feishu_sent=%s dry_run=%s",
        date_stamp,
        len(articles),
        sent,
        args.dry_run,
    )
    for item in results:
        LOGGER.info(
            "source_url=%s feishu=%s telegram=%s",
            item.get("source_url"),
            item.get("feishu"),
            item.get("telegram"),
        )
    return 0 if sent > 0 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
