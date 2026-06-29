from __future__ import annotations

import os
from typing import Any

from workflows.state import KBState

DEFAULT_TARGET_COUNT = 10


def _coerce_target_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_TARGET_COUNT


def plan_strategy(target_count: int | None = None) -> dict[str, Any]:
    """Return collection strategy settings for the requested target count."""
    target = _coerce_target_count(
        os.environ.get("PLANNER_TARGET_COUNT", DEFAULT_TARGET_COUNT)
        if target_count is None
        else target_count
    )

    if target < 10:
        return {
            "strategy": "lite",
            "target_count": target,
            "per_source_limit": 5,
            "relevance_threshold": 0.7,
            "max_iterations": 1,
            "collect_sources": ["github"],
            "rationale": "目标采集量较小，优先用较高相关性阈值和较少迭代快速得到精简结果。",
        }
    if target < 20:
        return {
            "strategy": "standard",
            "target_count": target,
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "collect_sources": ["github", "rss"],
            "rationale": "目标采集量适中，采用均衡的单源上限、相关性阈值和迭代次数。",
        }
    return {
        "strategy": "full",
        "target_count": target,
        "per_source_limit": 20,
        "relevance_threshold": 0.4,
        "max_iterations": 3,
        "collect_sources": ["github", "rss"],
        "rationale": "目标采集量较大，放宽相关性阈值并增加单源上限和迭代次数以扩大覆盖面。",
    }


def planner_node(state: KBState) -> dict[str, Any]:
    """LangGraph node wrapper for planner strategy generation."""
    plan = plan_strategy(state.get("target_count"))
    return {
        "plan": plan,
        "collect_limit": plan["per_source_limit"],
        "collect_sources": plan.get("collect_sources", ["github"]),
        "max_iterations": plan["max_iterations"],
        "relevance_threshold": plan["relevance_threshold"],
    }
