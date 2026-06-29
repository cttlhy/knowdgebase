#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflows.distribution import (
    DEFAULT_DIGEST_LIMIT,
    format_daily_digest,
    mark_articles_distributed,
    send_daily_digest_to_feishu,
    send_daily_digest_to_feishu_webhook,
)
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


def count_daily_articles(articles_dir: Path, *, date_stamp: str) -> int:
    pattern = f"{date_stamp}-*.json"
    return sum(
        1
        for path in articles_dir.glob(pattern)
        if path.name != "index.json" and str(_load_article(path).get("summary") or "").strip()
    )


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
    parser = argparse.ArgumentParser(description="Send one daily digest message to Feishu.")
    parser.add_argument("--env-file", default=str(ROOT_DIR / ".env"))
    parser.add_argument("--date", default="", help="Article date stamp YYYYMMDD (default: today UTC)")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_DIGEST_LIMIT,
        help="Max articles included in the digest",
    )
    parser.add_argument("--all", action="store_true", help="Include all matching articles in the digest")
    parser.add_argument(
        "--include-sent",
        action="store_true",
        help="Include articles already marked distribution.feishu=true",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print digest without sending")
    parser.add_argument("--print", action="store_true", help="Print digest text to stdout")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    apply_env_file(Path(args.env_file))

    feishu = resolve_feishu_app_config({})
    if not feishu_app_is_configured(feishu) and not args.dry_run:
        LOGGER.error("Feishu app is not fully configured (need APP_ID, APP_SECRET, RECEIVE_ID).")
        return 1

    date_stamp = args.date.strip() or _today_compact()
    articles_dir = ROOT_DIR / "knowledge" / "articles"
    total_count = count_daily_articles(articles_dir, date_stamp=date_stamp)
    articles = collect_daily_articles(
        articles_dir,
        date_stamp=date_stamp,
        limit=max(1, args.limit),
        send_all=args.all,
        only_new=not args.include_sent,
    )
    if not articles:
        LOGGER.info("No new articles to include in digest for date=%s", date_stamp)
        return 0

    digest_limit = len(articles) if args.all else max(1, args.limit)
    digest_text = format_daily_digest(
        articles,
        date_stamp=date_stamp,
        total_count=total_count,
        digest_limit=digest_limit,
    )
    if args.print or args.dry_run:
        print(digest_text)

    sent = False
    feishu_webhook = str(os.getenv("FEISHU_WEBHOOK_URL", "")).strip()
    try:
        if feishu_app_is_configured(feishu):
            sent = send_daily_digest_to_feishu(
                articles,
                app_id=feishu["app_id"],
                app_secret=feishu["app_secret"],
                receive_id=feishu["receive_id"],
                receive_id_type=feishu["receive_id_type"],
                date_stamp=date_stamp,
                total_count=total_count,
                digest_limit=digest_limit,
                dry_run=args.dry_run,
            )
        elif feishu_webhook and not args.dry_run:
            sent = send_daily_digest_to_feishu_webhook(
                articles,
                webhook_url=feishu_webhook,
                date_stamp=date_stamp,
                total_count=total_count,
                digest_limit=digest_limit,
            )
        elif args.dry_run:
            sent = True
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Daily digest send failed: %s", exc)
        return 1

    if sent and not args.dry_run:
        for article in articles:
            article.pop("_file", None)
        mark_articles_distributed(
            articles_dir,
            articles,
            feishu=True,
            digest_date=date_stamp,
        )

    LOGGER.info(
        "Daily digest finished for %s: included=%s total=%s sent=%s dry_run=%s",
        date_stamp,
        len(articles[:digest_limit]),
        total_count,
        sent,
        args.dry_run,
    )
    return 0 if sent or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
