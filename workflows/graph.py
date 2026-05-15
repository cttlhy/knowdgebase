from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from workflows.nodes import (
    analyze_node,
    collect_node,
    organize_node,
    review_node,
    save_node,
)
from workflows.state import KBState

LOGGER = logging.getLogger(__name__)


def _review_wrapper(state: KBState) -> dict[str, Any]:
    """Wrap review node to expose review_passed and advance iteration counter."""
    current_iteration = int(state.get("iteration", 0))
    update = review_node(state)
    review_payload = update.get("review") if isinstance(update.get("review"), dict) else {}
    passed = bool(review_payload.get("passed", False))
    return {
        **update,
        "review_passed": passed,
        # 每次经过 review 都增加迭代计数，供 organize_node 的修正逻辑使用。
        "iteration": current_iteration + 1,
    }


def review_router(state: KBState) -> str:
    """Route after review: pass => save, fail => organize."""
    if bool(state.get("review_passed", False)):
        return "pass"
    return "retry"


def build_graph():
    """Build and compile the knowledge-base LangGraph workflow app."""
    graph = StateGraph(KBState)

    # Register workflow nodes.
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", _review_wrapper)
    graph.add_node("save", save_node)

    # Linear path: collect -> analyze -> organize -> review.
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    # Conditional branch after review.
    graph.add_conditional_edges(
        "review",
        review_router,
        {
            "pass": "save",
            "retry": "organize",
        },
    )

    graph.set_entry_point("collect")
    graph.add_edge("save", END)
    return graph.compile()


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
    if node_name == "save":
        print(
            "[save] saved_count={} index_count={}".format(
                payload.get("saved_count", 0),
                payload.get("index_count", 0),
            )
        )
        return
    print(f"[{node_name}] {json.dumps(payload, ensure_ascii=False)[:200]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    app = build_graph()

    # 这里给出一个可运行的最小初始状态，便于本地直接执行图流程。
    initial_state: KBState = {
        "collect_limit": 5,
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
