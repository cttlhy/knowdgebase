from __future__ import annotations

import json
import logging
import re
from hashlib import sha1
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.model_client import Usage, chat_json
from workflows import reviewer as reviewer_module
from workflows._utils import coerce_bool, safe_float
from workflows.runtime_guards import (
    merge_guard_updates,
    prepare_untrusted_llm_input,
    record_llm_usage,
    sanitize_llm_output,
)
from workflows.schema import build_index_entry, canonicalize_article, resolve_source_url
from workflows.security import sanitize_for_persistence
from workflows.sources import collect_from_sources
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_score(raw_score: Any) -> float:
    score = safe_float(raw_score, default=0.0)
    if score > 1.0 and score <= 10.0:
        score = score / 10.0
    return max(0.0, min(1.0, score))


def _coerce_bool(value: Any, default: bool = False) -> bool:
    return coerce_bool(value, default)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(text or "")).strip("-").lower()
    return slug[:80] or "article"


def collect_node(state: KBState) -> dict[str, Any]:
    """Collect AI-related content from configured sources (GitHub, RSS)."""
    LOGGER.info("[collect_node] Start collecting from sources")
    limit = max(1, min(int(state.get("collect_limit", 20)), 100))
    query = str(state.get("github_query") or "ai OR llm OR agent")
    token = str(state.get("github_token") or "").strip()
    plan = state.get("plan") or {}
    raw_sources = state.get("collect_sources") or plan.get("collect_sources") or ["github"]
    if isinstance(raw_sources, str):
        raw_sources = [item.strip() for item in raw_sources.split(",") if item.strip()]

    collected, errors = collect_from_sources(
        sources=list(raw_sources),
        limit=limit,
        github_query=query,
        github_token=token,
    )
    result: dict[str, Any] = {"raw_items": collected}
    if errors:
        result["collect_error"] = "; ".join(errors)
    return result


def analyze_node(state: KBState) -> dict[str, Any]:
    """Analyze each collected item with LLM and return summary/tags/score."""
    LOGGER.info("[analyze_node] Start LLM analysis")
    raw_items = state.get("raw_items") or []
    analyzed: list[dict[str, Any]] = []
    runtime_state: KBState = {**state}
    system_prompt = "你是 AI 知识库分析助手。请输出结构化 JSON。"
    for item in raw_items:
        source_id = str(item.get("url") or item.get("title") or "unknown-source")
        untrusted_fragment, guard_update = prepare_untrusted_llm_input(
            runtime_state,
            item,
            source_id=source_id,
            stage="analyze",
        )
        runtime_state = merge_guard_updates(runtime_state, guard_update)
        prompt = (
            "请根据下面条目输出 JSON，字段必须包含："
            "summary(中文摘要，80字以内), tags(字符串数组), score(0~1浮点数), reason(中文)。\n"
            f"{untrusted_fragment}"
        )
        payload, usage = chat_json(prompt=prompt, system_prompt=system_prompt)
        runtime_state = merge_guard_updates(
            runtime_state,
            record_llm_usage(runtime_state, "analyze", usage),
        )
        payload, guard_update = sanitize_llm_output(
            runtime_state,
            payload,
            source_id=source_id,
            stage="analyze.metadata",
        )
        runtime_state = merge_guard_updates(runtime_state, guard_update)
        tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()][:8]
        candidate = {
            **item,
            "summary": str(payload.get("summary") or "").strip(),
            "tags": tags,
            "score": _normalize_score(payload.get("score")),
            "reason": str(payload.get("reason") or "").strip(),
        }
        candidate, guard_update = sanitize_llm_output(
            runtime_state,
            candidate,
            source_id=source_id,
            stage="analyze.item",
        )
        runtime_state = merge_guard_updates(runtime_state, guard_update)
        analyzed.append(candidate)
    return {
        "analyses": analyzed,
        "analyzed_items": analyzed,
        "security_risk_flags": runtime_state.get("security_risk_flags", []),
        "security_events": runtime_state.get("security_events", []),
        "cost_tracker": runtime_state.get("cost_tracker", {}),
        "cost_guard_report": runtime_state.get("cost_guard_report", {}),
        "token_usage": runtime_state.get("token_usage", {}),
        "total_cost_usd": runtime_state.get("total_cost_usd", 0.0),
    }


def organize_node(state: KBState) -> dict[str, Any]:
    """Filter and deduplicate reviewed analysis items into articles."""
    LOGGER.info("[organize_node] Start organizing articles")
    analyzed = state.get("analyzed_items") or []
    plan = state.get("plan") or {}
    relevance_threshold = safe_float(
        state.get("relevance_threshold", plan.get("relevance_threshold", 0.6)),
        default=0.6,
    )

    deduped: dict[str, dict[str, Any]] = {}
    for item in analyzed:
        score = _normalize_score(item.get("score"))
        url = resolve_source_url(item)
        if not url or score < relevance_threshold:
            continue
        candidate = {**item, "score": score}
        existing = deduped.get(url)
        if existing is None or _normalize_score(existing.get("score")) < score:
            deduped[url] = candidate

    return {"articles": list(deduped.values())}


def review_node(state: KBState) -> dict[str, Any]:
    """Review analyzed items through the dedicated reviewer module."""
    return reviewer_module.review_node(state, chat_json_func=chat_json)


def save_node(state: KBState) -> dict[str, Any]:
    """Persist articles and update index file under knowledge/articles."""
    LOGGER.info("[save_node] Start saving articles")
    articles = state.get("articles") or []
    repo_root = Path(str(state.get("knowledge_root") or Path(__file__).resolve().parent.parent))
    articles_dir = repo_root / "knowledge" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    _now = datetime.now(UTC)
    now = _now.isoformat()
    date_stamp = _now.strftime("%Y%m%d")

    saved_files: list[str] = []
    index_entries: list[dict[str, Any]] = []
    for index, article in enumerate(articles, start=1):
        canonical = canonicalize_article(article, index=index, now=now)
        payload = sanitize_for_persistence(canonical)
        unique_source = resolve_source_url(payload) or payload["id"]
        unique_suffix = sha1(unique_source.encode("utf-8")).hexdigest()[:10]
        filename = f"{date_stamp}-{_slugify(payload.get('title', payload['id']))}-{unique_suffix}.json"
        target = articles_dir / filename
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_files.append(target.name)
        index_entries.append(build_index_entry(payload, filename=filename, now=now))

    index_path = articles_dir / "index.json"
    existing_entries: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing_entries = loaded
        except json.JSONDecodeError:
            existing_entries = []

    merged = {
        resolve_source_url(item) or str(item.get("id")): item for item in existing_entries
    }
    for item in index_entries:
        merged[resolve_source_url(item) or str(item.get("id"))] = item
    merged_index = list(merged.values())
    index_path.write_text(json.dumps(merged_index, ensure_ascii=False, indent=2), encoding="utf-8")
    if articles:
        saved_files.append(index_path.name)
    return {"saved_count": len(articles), "saved_files": saved_files, "index_count": len(merged_index)}
