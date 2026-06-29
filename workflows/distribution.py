from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from workflows.feishu_app import feishu_app_is_configured, resolve_feishu_app_config, send_text_message
from workflows.schema import resolve_source_url
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)


def _post_json(url: str, payload: dict[str, Any], *, timeout: int = 15) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def _format_message(article: dict[str, Any], *, markdown: bool = True) -> str:
    tags = ", ".join(str(tag) for tag in article.get("tags", [])[:6])
    title = str(article.get("title", "Untitled"))
    if markdown:
        title = f"*{title}*"
    return (
        f"{title}\n"
        f"{article.get('summary', '')}\n"
        f"Score: {article.get('score', 0)}\n"
        f"Tags: {tags}\n"
        f"{resolve_source_url(article)}"
    )


def distribute_to_telegram(article: dict[str, Any], *, bot_token: str, chat_id: str) -> bool:
    """Send one article summary to Telegram."""
    if not bot_token.strip() or not chat_id.strip():
        return False
    message = _format_message(article)
    params = urllib.parse.urlencode(
        {
            "chat_id": chat_id.strip(),
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "false",
        }
    )
    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage?{params}"
    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        return 200 <= response.status < 300


def distribute_to_feishu_webhook(article: dict[str, Any], *, webhook_url: str) -> bool:
    """Send one article summary to a Feishu custom group bot webhook."""
    if not webhook_url.strip():
        return False
    payload = {
        "msg_type": "text",
        "content": {"text": _format_message(article, markdown=False)},
    }
    status, _ = _post_json(webhook_url.strip(), payload)
    return 200 <= status < 300


def distribute_to_feishu_app(
    article: dict[str, Any],
    *,
    app_id: str,
    app_secret: str,
    receive_id: str,
    receive_id_type: str = "chat_id",
) -> bool:
    """Send one article summary via Feishu enterprise self-built app bot."""
    return send_text_message(
        app_id=app_id,
        app_secret=app_secret,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        text=_format_message(article, markdown=False),
    )


def distribute_to_feishu(article: dict[str, Any], *, webhook_url: str) -> bool:
    """Backward-compatible alias for webhook-based Feishu delivery."""
    return distribute_to_feishu_webhook(article, webhook_url=webhook_url)


def distribute_node(state: KBState) -> dict[str, Any]:
    """Mark and optionally send newly saved articles to configured channels."""
    articles = state.get("articles") or []
    if not articles:
        return {"distribution_results": []}

    telegram_token = str(state.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    telegram_chat = str(state.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    feishu_webhook = str(state.get("feishu_webhook_url") or os.getenv("FEISHU_WEBHOOK_URL", "")).strip()
    feishu_app = resolve_feishu_app_config(state)
    dry_run = bool(state.get("distribution_dry_run", False))

    repo_root = Path(str(state.get("knowledge_root") or Path(__file__).resolve().parent.parent))
    articles_dir = repo_root / "knowledge" / "articles"
    results: list[dict[str, Any]] = []

    for article in articles:
        source_url = resolve_source_url(article)
        distribution = dict(article.get("distribution") or {"telegram": False, "feishu": False})
        result = {"source_url": source_url, "telegram": False, "feishu": False, "dry_run": dry_run}

        if not dry_run and telegram_token and telegram_chat:
            try:
                result["telegram"] = distribute_to_telegram(
                    article,
                    bot_token=telegram_token,
                    chat_id=telegram_chat,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("[distribute_node] telegram failed for %s: %s", source_url, exc)

        if not dry_run and feishu_app_is_configured(feishu_app):
            try:
                result["feishu"] = distribute_to_feishu_app(
                    article,
                    app_id=feishu_app["app_id"],
                    app_secret=feishu_app["app_secret"],
                    receive_id=feishu_app["receive_id"],
                    receive_id_type=feishu_app["receive_id_type"],
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("[distribute_node] feishu app failed for %s: %s", source_url, exc)
        elif not dry_run and feishu_webhook:
            try:
                result["feishu"] = distribute_to_feishu_webhook(article, webhook_url=feishu_webhook)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("[distribute_node] feishu webhook failed for %s: %s", source_url, exc)

        distribution["telegram"] = distribution.get("telegram", False) or result["telegram"]
        distribution["feishu"] = distribution.get("feishu", False) or result["feishu"]
        article["distribution"] = distribution

        article_id = str(article.get("id") or "")
        if article_id and articles_dir.exists():
            for path in articles_dir.glob("*.json"):
                if path.name == "index.json":
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if str(payload.get("id")) == article_id:
                    payload["distribution"] = distribution
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    break

        results.append(result)

    return {"distribution_results": results, "articles": articles}
