from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from workflows._utils import coerce_bool
from workflows.distribution import distribute_node
from workflows.human_flag import human_flag_node
from workflows.nodes import (
    analyze_node,
    collect_node,
    organize_node,
    review_node,
    save_node,
)
from workflows.planner import planner_node
from workflows.reviser import revise_node
from workflows.runtime_guards import check_workflow_budget, merge_guard_updates
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    return coerce_bool(value, default)


def _review_wrapper(state: KBState) -> dict[str, Any]:
    """Keep graph node indirection while letting review_node own review state."""
    return review_node(state)


def route_after_review(state: KBState) -> str:
    """Route review results through organize, revise, or manual fallback."""
    if _coerce_bool(state.get("review_passed", False), default=False):
        return "organize"
    iteration = int(state.get("iteration", 0))
    max_iterations = int(state.get("max_iterations", 3))
    if iteration >= max_iterations:
        return "human_flag"
    return "revise"


def build_graph():
    """Build and compile the knowledge-base LangGraph workflow app."""
    graph = StateGraph(KBState)

    # Register workflow nodes.
    graph.add_node("planner", planner_node)
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", _review_wrapper)
    graph.add_node("revise", revise_node)
    graph.add_node("human_flag", human_flag_node)
    graph.add_node("save", save_node)
    graph.add_node("distribute", distribute_node)

    # Linear path: planner -> collect -> analyze -> review.
    graph.add_edge("planner", "collect")
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "review")

    # Conditional branch after review.
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    graph.set_entry_point("planner")
    graph.add_edge("organize", "save")
    graph.add_edge("save", "distribute")
    graph.add_edge("revise", "review")
    graph.add_edge("human_flag", END)
    graph.add_edge("distribute", END)
    return graph.compile()


def run_workflow_with_guards(initial_state: KBState, *, app: Any | None = None) -> KBState:
    """Run the compiled graph with workflow-level budget checks before and after."""

    checked_state = merge_guard_updates(initial_state, check_workflow_budget(initial_state))
    active_app = app or build_graph()
    result = active_app.invoke(checked_state)
    if not isinstance(result, dict):
        raise TypeError("workflow app.invoke must return a state dictionary")
    return merge_guard_updates(result, check_workflow_budget(result))


def _print_node_output(node_name: str, payload: dict[str, Any]) -> None:
    """Print concise per-node outputs for local debugging."""
    if node_name == "collect":
        print(f"[collect] raw_items={len(payload.get('raw_items') or [])}")
        return
    if node_name == "analyze":
        token_usage = payload.get("token_usage") or {}
        print(
            "[analyze] analyzed_items={} total_tokens={} total_cost_usd={}".format(
                len(payload.get("analyzed_items") or []),
                token_usage.get("total_tokens", 0),
                payload.get("total_cost_usd", 0.0),
            )
        )
        return
    if node_name == "organize":
        print(f"[organize] articles={len(payload.get('articles') or [])}")
        return
    if node_name == "review":
        review = payload.get("review") or {}
        print(
            "[review] passed={} overall_score={} feedback={}".format(
                review.get("passed", False),
                review.get("overall_score", 0.0),
                str(review.get("feedback", ""))[:120],
            )
        )
        return
    if node_name == "human_flag":
        print(
            "[human_flag] flagged_count={} dir={}".format(
                payload.get("human_flagged_count", 0),
                payload.get("human_flag_dir", ""),
            )
        )
        return
    if node_name == "save":
        print(
            "[save] saved_count={} index_count={}".format(
                payload.get("saved_count", 0),
                payload.get("index_count", 0),
            )
        )
        return
    if node_name == "distribute":
        print(
            "[distribute] results={}".format(
                len(payload.get("distribution_results") or []),
            )
        )
        return
    print(f"[{node_name}] {json.dumps(payload, ensure_ascii=False)[:200]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    app = build_graph()

    # 这里给出一个可运行的最小初始状态，便于本地直接执行图流程。
    initial_state: KBState = {
        "target_count": 5,
        "github_query": "ai OR llm OR agent",
        "iteration": 0,
        "provider": "deepseek",
    }

    # stream 返回每步增量结果：{node_name: update_dict}
    for event in app.stream(initial_state):
        if not isinstance(event, dict):
            continue
        for node_name, payload in event.items():
            if isinstance(payload, dict):
                _print_node_output(node_name, payload)
