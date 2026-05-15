from __future__ import annotations

from typing import Any, TypedDict


class TokenUsageState(TypedDict):
    """Token usage summary tracked across workflow nodes."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class KBState(TypedDict, total=False):
    """State object passed between LangGraph workflow nodes."""

    github_query: str
    collect_limit: int
    github_token: str
    provider: str
    knowledge_root: str

    raw_items: list[dict[str, Any]]
    analyzed_items: list[dict[str, Any]]
    articles: list[dict[str, Any]]

    iteration: int
    review_passed: bool
    feedback: str
    review: dict[str, Any]

    token_usage: TokenUsageState
    total_cost_usd: float
    saved_count: int
    saved_files: list[str]
