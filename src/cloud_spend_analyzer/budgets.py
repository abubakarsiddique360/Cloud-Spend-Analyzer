"""Budget limits loaded from a small JSON document."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from cloud_spend_analyzer.models import CostError, CostRow

KNOWN_KEYS = ("monthly", "per_service", "per_account")


@dataclass(frozen=True)
class Breach:
    scope: str
    name: str
    month: str
    limit: float
    actual: float

    @property
    def over(self) -> float:
        return max(self.actual - self.limit, 0.0)

    @property
    def percent(self) -> float:
        if self.limit <= 0:
            return 0.0
        return self.over / self.limit * 100.0

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "name": self.name,
            "month": self.month,
            "limit": round(self.limit, 2),
            "actual": round(self.actual, 2),
            "over": round(self.over, 2),
            "percent": round(self.percent, 1),
        }


@dataclass
class Budget:
    monthly: float | None = None
    per_service: dict[str, float] = field(default_factory=dict)
    per_account: dict[str, float] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return self.monthly is None and not self.per_service and not self.per_account


def _limits(raw: Any, field_name: str) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CostError(f"{field_name} must be an object of name: limit")
    limits: dict[str, float] = {}
    for name, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise CostError(f"{field_name}.{name} must be a number")
        if value <= 0:
            raise CostError(f"{field_name}.{name} must be greater than zero")
        limits[str(name)] = float(value)
    return limits


def load_budget(payload: str | dict) -> Budget:
    """Parse budget JSON, rejecting unknown keys so typos never pass silently."""
    document: Any = payload
    if isinstance(payload, str):
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CostError(f"budget is not valid JSON: {exc.msg}") from exc
    if not isinstance(document, dict):
        raise CostError("budget must be a JSON object")

    unknown = sorted(set(document) - set(KNOWN_KEYS))
    if unknown:
        raise CostError(f"unknown budget key(s): {', '.join(unknown)}")

    monthly = document.get("monthly")
    if monthly is not None:
        if isinstance(monthly, bool) or not isinstance(monthly, int | float):
            raise CostError("monthly must be a number")
        if monthly <= 0:
            raise CostError("monthly must be greater than zero")
        monthly = float(monthly)

    budget = Budget(
        monthly=monthly,
        per_service=_limits(document.get("per_service"), "per_service"),
        per_account=_limits(document.get("per_account"), "per_account"),
    )
    if budget.empty:
        raise CostError("budget defines no limits")
    return budget


def _per_month(rows: list[CostRow], pick: str | None) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], float] = {}
    for row in rows:
        name = "all" if pick is None else getattr(row, pick)
        key = (row.month, name)
        totals[key] = totals.get(key, 0.0) + row.amount
    return totals


def check_budget(budget: Budget, rows: list[CostRow]) -> list[Breach]:
    """Return every month where a limit was exceeded, worst overspend first."""
    breaches: list[Breach] = []

    if budget.monthly is not None:
        for (month, _), actual in _per_month(rows, None).items():
            if actual > budget.monthly:
                breaches.append(Breach("monthly", "total", month, budget.monthly, actual))

    for pick, scope, limits in (
        ("service", "service", budget.per_service),
        ("account", "account", budget.per_account),
    ):
        if not limits:
            continue
        for (month, name), actual in _per_month(rows, pick).items():
            limit = limits.get(name)
            if limit is not None and actual > limit:
                breaches.append(Breach(scope, name, month, limit, actual))

    breaches.sort(key=lambda breach: breach.over, reverse=True)
    return breaches
