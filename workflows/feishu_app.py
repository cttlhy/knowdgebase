from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

LOGGER = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
DEFAULT_RECEIVE_ID_TYPE = "chat_id"
VALID_RECEIVE_ID_TYPES = frozenset({"open_id", "user_id", "union_id", "email", "chat_id"})

_token_cache: dict[str, Any] = {"token": "", "expires_at": 0.0}


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url=url, data=body, headers=request_headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"Feishu API returned non-object response from {url}")
    return data


def _get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 15) -> dict[str, Any]:
    request_headers = dict(headers or {})
    request = urllib.request.Request(url=url, headers=request_headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError(f"Feishu API returned non-object response from {url}")
    return data


def _authorized_get(path: str, *, app_id: str, app_secret: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
    token = get_tenant_access_token(app_id, app_secret)
    params = urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v not in (None, "")})
    url = f"{FEISHU_API_BASE}{path}"
    if params:
        url = f"{url}?{params}"
    payload = _get_json(url, headers={"Authorization": f"Bearer {token}"})
    if payload.get("code") != 0:
        raise RuntimeError(f"Feishu API request failed: {_api_error_message(payload)}")
    return payload


def _api_error_message(payload: dict[str, Any]) -> str:
    code = payload.get("code", "unknown")
    msg = payload.get("msg") or payload.get("message") or "unknown error"
    return f"code={code}, msg={msg}"


def get_tenant_access_token(app_id: str, app_secret: str, *, force_refresh: bool = False) -> str:
    """Fetch and cache tenant_access_token for an enterprise self-built app."""
    app_id = app_id.strip()
    app_secret = app_secret.strip()
    if not app_id or not app_secret:
        raise ValueError("feishu app_id and app_secret are required")

    now = time.time()
    if (
        not force_refresh
        and _token_cache.get("app_id") == app_id
        and _token_cache.get("token")
        and now < float(_token_cache.get("expires_at", 0))
    ):
        return str(_token_cache["token"])

    payload = _post_json(
        f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    if payload.get("code") != 0:
        raise RuntimeError(f"Feishu token request failed: {_api_error_message(payload)}")

    token = str(payload.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError("Feishu token response missing tenant_access_token")

    expire_seconds = int(payload.get("expire") or 7200)
    _token_cache.update(
        {
            "app_id": app_id,
            "token": token,
            "expires_at": now + max(expire_seconds - 120, 60),
        }
    )
    return token


def send_text_message(
    *,
    app_id: str,
    app_secret: str,
    receive_id: str,
    text: str,
    receive_id_type: str = DEFAULT_RECEIVE_ID_TYPE,
) -> bool:
    """Send a plain-text message via Feishu enterprise app bot."""
    receive_id = receive_id.strip()
    receive_id_type = (receive_id_type or DEFAULT_RECEIVE_ID_TYPE).strip()
    if receive_id_type not in VALID_RECEIVE_ID_TYPES:
        raise ValueError(f"unsupported feishu receive_id_type: {receive_id_type}")
    if not receive_id:
        raise ValueError("feishu receive_id is required")

    token = get_tenant_access_token(app_id, app_secret)
    query = urllib.parse.urlencode({"receive_id_type": receive_id_type})
    payload = _post_json(
        f"{FEISHU_API_BASE}/im/v1/messages?{query}",
        {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    if payload.get("code") != 0:
        raise RuntimeError(f"Feishu message send failed: {_api_error_message(payload)}")
    return True


def resolve_feishu_app_config(state: dict[str, Any]) -> dict[str, str]:
    """Read Feishu app credentials from workflow state or environment."""
    import os

    return {
        "app_id": str(state.get("feishu_app_id") or os.getenv("FEISHU_APP_ID", "")).strip(),
        "app_secret": str(state.get("feishu_app_secret") or os.getenv("FEISHU_APP_SECRET", "")).strip(),
        "receive_id": str(state.get("feishu_receive_id") or os.getenv("FEISHU_RECEIVE_ID", "")).strip(),
        "receive_id_type": str(
            state.get("feishu_receive_id_type")
            or os.getenv("FEISHU_RECEIVE_ID_TYPE", DEFAULT_RECEIVE_ID_TYPE)
        ).strip()
        or DEFAULT_RECEIVE_ID_TYPE,
    }


def feishu_app_is_configured(config: dict[str, str]) -> bool:
    return bool(config.get("app_id") and config.get("app_secret") and config.get("receive_id"))


def list_bot_chats(
    *,
    app_id: str,
    app_secret: str,
    page_size: int = 100,
    query: str = "",
) -> list[dict[str, Any]]:
    """List group chats where the app bot is a member."""
    app_id = app_id.strip()
    app_secret = app_secret.strip()
    if not app_id or not app_secret:
        raise ValueError("feishu app_id and app_secret are required")

    chats: list[dict[str, Any]] = []
    page_token = ""
    while True:
        if query.strip():
            payload = _authorized_get(
                "/im/v1/chats/search",
                app_id=app_id,
                app_secret=app_secret,
                query={
                    "query": query.strip(),
                    "page_size": page_size,
                    "page_token": page_token,
                },
            )
        else:
            payload = _authorized_get(
                "/im/v1/chats",
                app_id=app_id,
                app_secret=app_secret,
                query={"page_size": page_size, "page_token": page_token},
            )

        data = payload.get("data") or {}
        for item in data.get("items") or []:
            if isinstance(item, dict):
                chats.append(
                    {
                        "chat_id": str(item.get("chat_id") or ""),
                        "name": str(item.get("name") or ""),
                        "description": str(item.get("description") or ""),
                        "external": bool(item.get("external", False)),
                        "chat_status": str(item.get("chat_status") or ""),
                    }
                )

        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "")
        if not page_token:
            break
    return [chat for chat in chats if chat.get("chat_id")]
