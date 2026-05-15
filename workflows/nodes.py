from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.model_client import Usage, calculate_cost_usd, chat, chat_json
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)
GITHUB_SEARCH_API = "https://api.github.com/search/repositories"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_score(raw_score: Any) -> float:
    score = _safe_float(raw_score, default=0.0)
    if score > 1.0 and score <= 10.0:
        score = score / 10.0
    return max(0.0, min(1.0, score))


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(text or "")).strip("-").lower()
    return slug[:80] or "article"


def _usage_delta(state: KBState, usage: Usage) -> dict[str, Any]:
    previous = state.get("token_usage") or {}
    prompt_tokens = int(previous.get("prompt_tokens", 0)) + usage.prompt_tokens
    completion_tokens = int(previous.get("completion_tokens", 0)) + usage.completion_tokens
    total_tokens = int(previous.get("total_tokens", 0)) + usage.total_tokens
    provider = str(state.get("provider") or "deepseek")
    prev_cost = _safe_float(state.get("total_cost_usd"), default=0.0)
    added_cost = calculate_cost_usd(provider=provider, usage=usage)
    return {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        "total_cost_usd": round(prev_cost + added_cost, 8),
    }


def _sum_usage(current: Usage, added: Usage) -> Usage:
    return Usage(
        prompt_tokens=current.prompt_tokens + added.prompt_tokens,
        completion_tokens=current.completion_tokens + added.completion_tokens,
        total_tokens=current.total_tokens + added.total_tokens,
        estimated=current.estimated and added.estimated,
    )


def collect_node(state: KBState) -> dict[str, Any]:
    """Collect AI-related repositories from GitHub Search API."""
    LOGGER.info("[collect_node] Start collecting repositories")
    limit = max(1, min(int(state.get("collect_limit", 20)), 100))
    query = str(state.get("github_query") or "ai OR llm OR agent")
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
    )
    headers = {"Accept": "application/vnd.github+json"}
    token = str(state.get("github_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url=f"{GITHUB_SEARCH_API}?{params}",
        headers=headers,
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

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
    return {"raw_items": collected}


def analyze_node(state: KBState) -> dict[str, Any]:
    """Analyze each collected item with LLM and return summary/tags/score."""
    LOGGER.info("[analyze_node] Start LLM analysis")
    raw_items = state.get("raw_items") or []
    analyzed: list[dict[str, Any]] = []
    usage_total = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0, estimated=False)
    system_prompt = "你是 AI 知识库分析助手。请输出结构化 JSON。"
    for item in raw_items:
        summary_text, summary_usage = chat(
            prompt=(
                "请根据下面条目生成简洁中文摘要，80字以内。"
                "只输出摘要正文，不要额外解释。\n"
                f"标题: {item.get('title', '')}\n"
                f"链接: {item.get('url', '')}\n"
                f"内容: {item.get('content', '')}"
            ),
            system_prompt="你是中文技术编辑。",
        )
        usage_total = _sum_usage(usage_total, summary_usage)
        prompt = (
            "请根据下面条目和摘要输出 JSON，字段必须包含："
            "tags(字符串数组), score(0~1浮点数), reason(中文)。\n"
            f"标题: {item.get('title', '')}\n"
            f"链接: {item.get('url', '')}\n"
            f"摘要: {summary_text}"
        )
        payload, usage = chat_json(prompt=prompt, system_prompt=system_prompt)
        usage_total = _sum_usage(usage_total, usage)
        tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()][:8]
        analyzed.append(
            {
                **item,
                "summary": str(summary_text or "").strip(),
                "tags": tags,
                "score": _normalize_score(payload.get("score")),
                "reason": str(payload.get("reason") or "").strip(),
            }
        )
    return {"analyzed_items": analyzed, **_usage_delta(state, usage_total)}


def organize_node(state: KBState) -> dict[str, Any]:
    """Filter, deduplicate, and optionally revise items based on review feedback."""
    LOGGER.info("[organize_node] Start organizing articles")
    analyzed = state.get("analyzed_items") or []
    iteration = int(state.get("iteration", 0))
    feedback = str(state.get("feedback") or "").strip()

    deduped: dict[str, dict[str, Any]] = {}
    for item in analyzed:
        score = _normalize_score(item.get("score"))
        url = str(item.get("url") or "").strip()
        if not url or score < 0.6:
            continue
        candidate = {**item, "score": score}
        existing = deduped.get(url)
        if existing is None or _normalize_score(existing.get("score")) < score:
            deduped[url] = candidate

    usage_total = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0, estimated=False)
    if iteration > 0 and feedback:
        system_prompt = "你是知识条目修订助手。必须遵循审核意见。输出 JSON。"
        for url, article in list(deduped.items()):
            prompt = (
                "请根据审核反馈定向修正条目，输出 JSON，字段："
                "summary(中文), tags(数组), score(0~1), reason(中文)。\n"
                f"审核反馈: {feedback}\n"
                f"原始条目: {json.dumps(article, ensure_ascii=False)}"
            )
            payload, usage = chat_json(prompt=prompt, system_prompt=system_prompt)
            usage_total = _sum_usage(usage_total, usage)
            deduped[url] = {
                **article,
                "summary": str(payload.get("summary") or article.get("summary") or "").strip(),
                "tags": [
                    str(tag).strip()
                    for tag in payload.get("tags", article.get("tags", []))
                    if str(tag).strip()
                ][:8],
                "score": _normalize_score(payload.get("score", article.get("score"))),
                "reason": str(payload.get("reason") or article.get("reason") or "").strip(),
            }

    return {"articles": list(deduped.values()), **_usage_delta(state, usage_total)}


def review_node(state: KBState) -> dict[str, Any]:
    """Review organized articles with four-dimensional quality scores."""
    LOGGER.info("[review_node] Start article review")
    articles = state.get("articles") or []
    iteration = int(state.get("iteration", 0))
    prompt = (
        "请审核以下知识条目列表，并按要求返回 JSON："
        '{"passed": bool, "overall_score": float, "feedback": str, "scores": {...}}。'
        "scores 中必须包含四个字段：summary_quality, tag_accuracy, "
        "classification_rationale, consistency。\n"
        f"条目: {json.dumps(articles, ensure_ascii=False)}"
    )
    payload, usage = chat_json(prompt=prompt, system_prompt="你是严格的知识库审核员。请只返回 JSON。")
    review = {
        "passed": bool(payload.get("passed", False)),
        "overall_score": _normalize_score(payload.get("overall_score")),
        "feedback": str(payload.get("feedback") or "").strip(),
        "scores": payload.get("scores") if isinstance(payload.get("scores"), dict) else {},
    }
    if iteration >= 2:
        review["passed"] = True
        if not review["feedback"]:
            review["feedback"] = "达到最大迭代次数，强制通过。"
    return {"review": review, "feedback": review["feedback"], **_usage_delta(state, usage)}


def save_node(state: KBState) -> dict[str, Any]:
    """Persist articles and update index file under knowledge/articles."""
    LOGGER.info("[save_node] Start saving articles")
    articles = state.get("articles") or []
    repo_root = Path(str(state.get("knowledge_root") or Path(__file__).resolve().parent.parent))
    articles_dir = repo_root / "knowledge" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    now = _now_iso()

    saved_files: list[str] = []
    index_entries: list[dict[str, Any]] = []
    for index, article in enumerate(articles, start=1):
        article_id = str(article.get("id") or f"article-{datetime.now(UTC).strftime('%Y%m%d')}-{index:03d}")
        payload = {**article, "id": article_id, "updated_at": now}
        filename = f"{datetime.now(UTC).strftime('%Y%m%d')}-{_slugify(payload.get('title', article_id))}.json"
        target = articles_dir / filename
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_files.append(target.name)
        index_entries.append(
            {
                "id": article_id,
                "title": payload.get("title", ""),
                "url": payload.get("url", ""),
                "score": _normalize_score(payload.get("score")),
                "tags": payload.get("tags", []),
                "file": target.name,
                "updated_at": now,
            }
        )

    index_path = articles_dir / "index.json"
    existing_entries: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing_entries = loaded
        except json.JSONDecodeError:
            existing_entries = []

    merged = {str(item.get("url") or item.get("id")): item for item in existing_entries}
    for item in index_entries:
        merged[str(item.get("url") or item.get("id"))] = item
    merged_index = list(merged.values())
    index_path.write_text(json.dumps(merged_index, ensure_ascii=False, indent=2), encoding="utf-8")
    if articles:
        saved_files.append(index_path.name)
    return {"saved_count": len(articles), "saved_files": saved_files, "index_count": len(merged_index)}
