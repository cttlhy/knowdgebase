from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class BudgetExceededError(RuntimeError):
    """Raised when LLM spending exceeds the configured budget."""


@dataclass(frozen=True)
class CostRecord:
    timestamp: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    model: str
    provider: str


@dataclass(frozen=True)
class BudgetStatus:
    status: str
    total_cost: float
    budget: float
    usage_ratio: float
    message: str


class CostGuard:
    """Track LLM cost and fail fast when a configured budget is exceeded."""

    def __init__(
        self,
        budget: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
        *,
        currency: str = "yuan",
        enforce_on_record: bool = True,
    ) -> None:
        if budget <= 0:
            raise ValueError("budget must be greater than 0")
        if not 0 <= alert_threshold <= 1:
            raise ValueError("alert_threshold must be between 0 and 1")
        if input_price_per_million < 0 or output_price_per_million < 0:
            raise ValueError("token prices must be non-negative")
        if not currency.strip():
            raise ValueError("currency must not be empty")

        self.budget = float(budget)
        self.alert_threshold = float(alert_threshold)
        self.input_price_per_million = float(input_price_per_million)
        self.output_price_per_million = float(output_price_per_million)
        self.currency = currency.strip()
        self.enforce_on_record = enforce_on_record
        self.records: list[CostRecord] = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0

    def record(
        self,
        node_name: str,
        usage: Any,
        *,
        model: str = "",
        provider: str = "",
    ) -> CostRecord:
        """Record one LLM call and enforce the budget by default."""

        prompt_tokens = self._read_token_count(usage, "prompt_tokens")
        completion_tokens = self._read_token_count(usage, "completion_tokens")
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if not str(node_name).strip():
            raise ValueError("node_name must not be empty")

        cost = self._calculate_cost(prompt_tokens, completion_tokens)
        record = CostRecord(
            timestamp=datetime.now(UTC).isoformat(),
            node_name=str(node_name),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            model=str(model or ""),
            provider=str(provider or ""),
        )

        self.records.append(record)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost = round(self.total_cost + cost, 10)
        if self.enforce_on_record:
            self.check()
        return record

    def check(self) -> BudgetStatus:
        """Return current budget status, raising when the budget is exceeded."""

        return self._build_budget_status(raise_on_exceeded=True)

    def get_status(self) -> BudgetStatus:
        """Return current budget status without raising."""

        return self._build_budget_status(raise_on_exceeded=False)

    def get_report(self) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        for record in self.records:
            node = nodes.setdefault(
                record.node_name,
                {
                    "call_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "models": {},
                    "providers": {},
                },
            )
            node["call_count"] += 1
            node["prompt_tokens"] += record.prompt_tokens
            node["completion_tokens"] += record.completion_tokens
            node["total_tokens"] += record.prompt_tokens + record.completion_tokens
            node["cost"] = round(node["cost"] + record.cost, 10)
            if record.model:
                node["models"][record.model] = node["models"].get(record.model, 0) + 1
            if record.provider:
                node["providers"][record.provider] = node["providers"].get(record.provider, 0) + 1

        status = self.get_status()
        return {
            "budget": self.budget,
            "currency": self.currency,
            "alert_threshold": self.alert_threshold,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost": self.total_cost,
            "status": asdict(status),
            "nodes": nodes,
            "records": [asdict(record) for record in self.records],
        }

    def save_report(self, path: str | Path) -> Path:
        report_path = Path(path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(self.get_report(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report_path

    def _build_budget_status(self, raise_on_exceeded: bool) -> BudgetStatus:
        usage_ratio = self.total_cost / self.budget
        if self.total_cost > self.budget:
            message = (
                f"Budget exceeded: {self.total_cost:.6f} {self.currency} used "
                f"of {self.budget:.6f} {self.currency} budget."
            )
            if raise_on_exceeded:
                raise BudgetExceededError(message)
            status = "exceeded"
        elif usage_ratio >= self.alert_threshold:
            status = "warning"
            message = (
                f"Budget warning: {usage_ratio:.1%} used "
                f"({self.total_cost:.6f}/{self.budget:.6f} {self.currency})."
            )
        else:
            status = "ok"
            message = (
                f"Budget ok: {usage_ratio:.1%} used "
                f"({self.total_cost:.6f}/{self.budget:.6f} {self.currency})."
            )
        return BudgetStatus(
            status=status,
            total_cost=self.total_cost,
            budget=self.budget,
            usage_ratio=usage_ratio,
            message=message,
        )

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        input_cost = prompt_tokens * self.input_price_per_million / 1_000_000
        output_cost = completion_tokens * self.output_price_per_million / 1_000_000
        return round(input_cost + output_cost, 10)

    @staticmethod
    def _read_token_count(usage: Any, key: str) -> int:
        if isinstance(usage, dict):
            value = usage.get(key, 0)
        else:
            value = getattr(usage, key, 0)
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
