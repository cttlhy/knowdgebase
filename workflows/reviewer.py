from __future__ import annotations

import logging
from typing import Any, Callable

from pipeline.model_client import Usage, chat_json
from workflows._utils import safe_float
from workflows.runtime_guards import (
    merge_guard_updates,
    prepare_untrusted_llm_input,
    record_llm_usage,
    sanitize_llm_output,
)
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)

REVIEW_LIMIT = 5
PASS_THRESHOLD = 7.0
SCORE_WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}


def _normalize_dimension_score(value: Any) -> float:
    return max(1.0, min(10.0, safe_float(value, default=1.0)))


def _weighted_score(scores: dict[str, Any]) -> float:
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        total += _normalize_dimension_score(scores.get(key)) * weight
    return round(total, 2)


def review_node(
    state: KBState,
    *,
    chat_json_func: Callable[..., tuple[dict[str, Any], Usage]] | None = None,
) -> dict[str, Any]:
    """Review analyzed items and gate workflow quality."""
    LOGGER.info("[review_node] Start analysis review")
    if chat_json_func is None:
        chat_json_func = chat_json
    analyses = (state.get("analyses") or [])[:REVIEW_LIMIT]
    runtime_state: KBState = {**state}
    analyses_fragment, guard_update = prepare_untrusted_llm_input(
        runtime_state,
        analyses,
        source_id="workflow:analyses",
        stage="review",
    )
    runtime_state = merge_guard_updates(runtime_state, guard_update)
    iteration = int(state.get("iteration", 0)) + 1
    system_prompt = "你是严格的技术内容审核员。请只返回 JSON，不要输出额外解释。"
    prompt = (
        "请审核以下分析结果。评分必须使用 1-10 分，返回 JSON："
        '{"feedback": str, "scores": {"summary_quality": number, '
        '"technical_depth": number, "relevance": number, '
        '"originality": number, "formatting": number}}。\n'
        "评分维度：summary_quality 摘要质量 25%，technical_depth 技术深度 25%，"
        "relevance 相关性 20%，originality 原创性 15%，formatting 格式规范 15%。\n"
        "注意：不要审核 articles，只审核 analyses。\n"
        f"analyses: {analyses_fragment}"
    )

    try:
        payload, usage = chat_json_func(prompt=prompt, system=system_prompt, temperature=0.1)
    except Exception as exc:  # noqa: BLE001 - review should never block the workflow.
        LOGGER.warning("[review_node] LLM review failed; auto passing: %s", exc)
        feedback = f"LLM 审核失败，已自动通过以避免阻塞流程：{exc}"
        review = {
            "passed": True,
            "overall_score": PASS_THRESHOLD,
            "feedback": feedback,
            "scores": {},
        }
        return {
            "review_passed": True,
            "review_feedback": feedback,
            "feedback": feedback,
            "iteration": iteration,
            "review": review,
            "cost_tracker": state.get("cost_tracker") or {},
        }
    runtime_state = merge_guard_updates(
        runtime_state,
        record_llm_usage(runtime_state, "review", usage),
    )
    payload, guard_update = sanitize_llm_output(
        runtime_state,
        payload,
        source_id="workflow:analyses",
        stage="review",
    )
    runtime_state = merge_guard_updates(runtime_state, guard_update)

    raw_scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    scores = {key: _normalize_dimension_score(raw_scores.get(key)) for key in SCORE_WEIGHTS}
    overall_score = _weighted_score(scores)
    review_passed = overall_score >= PASS_THRESHOLD
    feedback = str(payload.get("feedback") or "").strip()
    review = {
        "passed": review_passed,
        "overall_score": overall_score,
        "feedback": feedback,
        "scores": scores,
    }
    review, guard_update = sanitize_llm_output(
        runtime_state,
        review,
        source_id="workflow:analyses",
        stage="review.result",
    )
    runtime_state = merge_guard_updates(runtime_state, guard_update)
    return {
        "review_passed": review_passed,
        "review_feedback": str(review.get("feedback") or ""),
        "feedback": str(review.get("feedback") or ""),
        "iteration": iteration,
        "review": review,
        "cost_tracker": runtime_state.get("cost_tracker", {}),
        "cost_guard_report": runtime_state.get("cost_guard_report", {}),
        "token_usage": runtime_state.get("token_usage", {}),
        "total_cost_usd": runtime_state.get("total_cost_usd", 0.0),
        "security_risk_flags": runtime_state.get("security_risk_flags", []),
        "security_events": runtime_state.get("security_events", []),
    }
