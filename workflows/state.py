from __future__ import annotations

from typing import Any, TypedDict


class TokenUsageState(TypedDict):
    """Token usage summary tracked across workflow nodes."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class KBState(TypedDict, total=False):
    """State object passed between LangGraph workflow nodes."""
    plan: dict
    target_count: int
    github_query: str
    collect_limit: int
    collect_sources: list[str]
    relevance_threshold: float
    github_token: str
    provider: str
    knowledge_root: str

    raw_items: list[dict[str, Any]]
    collect_error: str
    analyses: list[dict[str, Any]]
    analyzed_items: list[dict[str, Any]]
    articles: list[dict[str, Any]]

    iteration: int
    max_iterations: int
    review_passed: bool
    review_feedback: str
    feedback: str
    review: dict[str, Any]
    cost_tracker: dict[str, Any]
    cost_budget_usd: float
    cost_alert_threshold: float
    cost_guard_report: dict[str, Any]
    cost_budget_status: str
    security_risk_flags: list[str]
    security_events: list[dict[str, Any]]
    human_flagged: bool
    human_flagged_count: int
    human_flagged_files: list[str]
    human_flag_dir: str

    token_usage: TokenUsageState
    total_cost_usd: float
    saved_count: int
    saved_files: list[str]
    index_count: int

    telegram_bot_token: str
    telegram_chat_id: str
    feishu_webhook_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_receive_id: str
    feishu_receive_id_type: str
    distribution_dry_run: bool
    distribution_results: list[dict[str, Any]]

    human_review_promoted_count: int
    human_review_promoted: list[dict[str, Any]]
    auto_approve_human_flags: bool
    human_flag_files: list[str]
