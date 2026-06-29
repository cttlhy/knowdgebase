from __future__ import annotations

import logging
from typing import Any, Callable

from pipeline.model_client import Usage, chat_json
from workflows.runtime_guards import (
    merge_guard_updates,
    prepare_untrusted_llm_input,
    record_llm_usage,
    sanitize_llm_output,
)
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)


def revise_node(
    state: KBState,
    *,
    chat_json_func: Callable[..., tuple[dict[str, Any], Usage]] | None = None,
) -> dict[str, Any]:
    """Revise analyses according to review feedback."""
    LOGGER.info("[revise_node] Start revising analyses")
    analyses = state.get("analyses") or []
    feedback = str(state.get("review_feedback") or "").strip()
    if not analyses or not feedback:
        return {}

    if chat_json_func is None:
        chat_json_func = chat_json

    runtime_state: KBState = {**state}
    revision_fragment, guard_update = prepare_untrusted_llm_input(
        runtime_state,
        {"review_feedback": feedback, "analyses": analyses},
        source_id="workflow:revision-input",
        stage="revise",
    )
    runtime_state = merge_guard_updates(runtime_state, guard_update)
    system_prompt = "你是技术内容修订助手。请只返回 JSON，不要输出额外解释。"
    prompt = (
        "请根据审核反馈修改 analyses 列表，保留每个条目的原始身份字段，"
        "只改进 summary、tags、score、reason 等分析质量相关字段。"
        '返回 JSON：{"analyses": [修改后的分析条目列表]}。\n'
        f"{revision_fragment}"
    )
    payload, usage = chat_json_func(prompt=prompt, system=system_prompt, temperature=0.4)
    runtime_state = merge_guard_updates(
        runtime_state,
        record_llm_usage(runtime_state, "revise", usage),
    )
    payload, guard_update = sanitize_llm_output(
        runtime_state,
        payload,
        source_id="workflow:revision-input",
        stage="revise",
    )
    runtime_state = merge_guard_updates(runtime_state, guard_update)
    improved = payload.get("analyses")
    if not isinstance(improved, list):
        improved = analyses
    improved, guard_update = sanitize_llm_output(
        runtime_state,
        improved,
        source_id="workflow:revision-input",
        stage="revise.result",
    )
    runtime_state = merge_guard_updates(runtime_state, guard_update)

    return {
        "analyses": improved,
        "analyzed_items": improved,
        "cost_tracker": runtime_state.get("cost_tracker", {}),
        "cost_guard_report": runtime_state.get("cost_guard_report", {}),
        "token_usage": runtime_state.get("token_usage", {}),
        "total_cost_usd": runtime_state.get("total_cost_usd", 0.0),
        "security_risk_flags": runtime_state.get("security_risk_flags", []),
        "security_events": runtime_state.get("security_events", []),
    }
