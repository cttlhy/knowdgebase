from __future__ import annotations

from typing import Any

from pipeline.model_client import Usage
from workflows._utils import safe_float
from workflows.cost_guard import CostGuard
from workflows.security import AgentSecurityGuard, AuditEventType
from workflows.state import KBState

DEFAULT_COST_BUDGET_USD = 1.0
DEFAULT_COST_ALERT_THRESHOLD = 0.8

_PROVIDER_PRICING_USD_PER_MILLION = {
    "deepseek": {"input": 0.14, "output": 0.28},
    "qwen": {"input": 0.40, "output": 1.20},
    "openai": {"input": 0.15, "output": 0.60},
}


def prepare_untrusted_llm_input(
    state: KBState,
    payload: Any,
    *,
    source_id: str,
    stage: str,
) -> tuple[str, dict[str, Any]]:
    """Wrap external content as data before it is embedded in prompts."""

    guard = AgentSecurityGuard()
    context = guard.prepare_untrusted_context(payload, source_id=source_id)
    event = guard.audit_event(
        event_type=AuditEventType.LLM_INPUT_PREPARED,
        stage=stage,
        source_id=source_id,
        input_payload=payload,
        output_payload=context.prompt_fragment,
        risk_flags=context.risk_flags,
    )
    return context.prompt_fragment, _security_delta(state, context.risk_flags, [event.to_dict()])


def sanitize_llm_output(
    state: KBState,
    payload: Any,
    *,
    source_id: str,
    stage: str,
) -> tuple[Any, dict[str, Any]]:
    """Sanitize model output before it continues through the workflow."""

    guard = AgentSecurityGuard()
    sanitized = guard.sanitize_output(payload)
    risk_flags = guard.detect_risks(payload)
    event = guard.audit_event(
        event_type=AuditEventType.LLM_OUTPUT_SANITIZED,
        stage=stage,
        source_id=source_id,
        input_payload=payload,
        output_payload=sanitized,
        risk_flags=risk_flags,
    )
    return sanitized, _security_delta(state, risk_flags, [event.to_dict()])


def record_llm_usage(
    state: KBState,
    node_name: str,
    usage: Usage,
    *,
    model: str = "",
) -> dict[str, Any]:
    """Record one LLM call, update workflow cost state, and enforce budget."""

    provider = str(state.get("provider") or "deepseek").strip().lower()
    pricing = _PROVIDER_PRICING_USD_PER_MILLION.get(
        provider,
        _PROVIDER_PRICING_USD_PER_MILLION["deepseek"],
    )
    guard = _build_cost_guard(state, provider=provider, pricing=pricing)
    guard.record(node_name, usage, model=model, provider=provider)
    report = guard.get_report()
    total_prompt_tokens = int(report["total_prompt_tokens"])
    total_completion_tokens = int(report["total_completion_tokens"])
    total_tokens = int(report["total_tokens"])
    total_cost_usd = round(float(report["total_cost"]), 8)
    return {
        "cost_tracker": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
        },
        "token_usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        },
        "total_cost_usd": total_cost_usd,
        "cost_guard_report": report,
    }


def check_workflow_budget(state: KBState) -> dict[str, Any]:
    """Check the accumulated workflow budget without recording new usage."""

    provider = str(state.get("provider") or "deepseek").strip().lower()
    pricing = _PROVIDER_PRICING_USD_PER_MILLION.get(
        provider,
        _PROVIDER_PRICING_USD_PER_MILLION["deepseek"],
    )
    guard = _build_cost_guard(state, provider=provider, pricing=pricing)
    status = guard.check()
    report = guard.get_report()
    total_prompt_tokens = int(report["total_prompt_tokens"])
    total_completion_tokens = int(report["total_completion_tokens"])
    total_tokens = int(report["total_tokens"])
    total_cost_usd = round(float(report["total_cost"]), 8)
    return {
        "cost_tracker": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
        },
        "token_usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        },
        "total_cost_usd": total_cost_usd,
        "cost_guard_report": report,
        "cost_budget_status": status.status,
    }


def merge_guard_updates(state: KBState, *updates: dict[str, Any]) -> KBState:
    merged: KBState = {**state}
    for update in updates:
        merged.update(update)
    return merged


def _build_cost_guard(
    state: KBState,
    *,
    provider: str,
    pricing: dict[str, float],
) -> CostGuard:
    guard = CostGuard(
        budget=safe_float(state.get("cost_budget_usd"), DEFAULT_COST_BUDGET_USD),
        alert_threshold=safe_float(
            state.get("cost_alert_threshold"),
            DEFAULT_COST_ALERT_THRESHOLD,
        ),
        input_price_per_million=pricing["input"],
        output_price_per_million=pricing["output"],
        currency="usd",
        enforce_on_record=False,
    )
    for record in _existing_cost_records(state):
        guard.record(
            str(record.get("node_name") or "unknown"),
            {
                "prompt_tokens": int(record.get("prompt_tokens", 0)),
                "completion_tokens": int(record.get("completion_tokens", 0)),
            },
            model=str(record.get("model") or ""),
            provider=str(record.get("provider") or provider),
        )
    guard.enforce_on_record = True
    return guard


def _existing_cost_records(state: KBState) -> list[dict[str, Any]]:
    report = state.get("cost_guard_report")
    if isinstance(report, dict) and isinstance(report.get("records"), list):
        records = [record for record in report["records"] if isinstance(record, dict)]
        if records:
            return records
    tracker = state.get("cost_tracker")
    if isinstance(tracker, dict) and tracker:
        prompt_tokens = int(tracker.get("prompt_tokens", 0))
        completion_tokens = int(tracker.get("completion_tokens", 0))
        if prompt_tokens or completion_tokens:
            return [
                {
                    "node_name": "legacy",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "model": "",
                    "provider": state.get("provider") or "deepseek",
                }
            ]
    return []


def _security_delta(
    state: KBState,
    risk_flags: list[str],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_flags = set(str(flag) for flag in state.get("security_risk_flags", []))
    existing_events = list(state.get("security_events", []))
    return {
        "security_risk_flags": sorted(existing_flags.union(str(flag) for flag in risk_flags)),
        "security_events": existing_events + events,
    }


def _safe_float(value: Any, default: float) -> float:
    return safe_float(value, default)
