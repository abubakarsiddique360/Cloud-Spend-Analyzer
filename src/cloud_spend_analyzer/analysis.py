"""Aggregations that turn rows into the numbers people actually ask about."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import median

from cloud_spend_analyzer.models import CostRow


def _totals(rows: Iterable[CostRow], key: Callable[[CostRow], str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        name = key(row)
        totals[name] = totals.get(name, 0.0) + row.amount
    return totals


def monthly_totals(rows: Iterable[CostRow]) -> dict[str, float]:
    """Total spend per month, oldest first."""
    return dict(sorted(_totals(rows, lambda row: row.month).items()))


def service_totals(rows: Iterable[CostRow]) -> dict[str, float]:
    """Total spend per service, largest first."""
    return dict(sorted(_totals(rows, lambda row: row.service).items(), key=lambda pair: -pair[1]))


def account_totals(rows: Iterable[CostRow]) -> dict[str, float]:
    """Total spend per account, largest first."""
    return dict(sorted(_totals(rows, lambda row: row.account).items(), key=lambda pair: -pair[1]))


@dataclass(frozen=True)
class Change:
    service: str
    previous_month: str
    current_month: str
    previous: float
    current: float

    @property
    def delta(self) -> float:
        return self.current - self.previous

    @property
    def percent(self) -> float | None:
        if self.previous == 0:
            return None
        return self.delta / self.previous * 100.0

    def as_dict(self) -> dict:
        return {
            "service": self.service,
            "from_month": self.previous_month,
            "to_month": self.current_month,
            "previous": round(self.previous, 2),
            "current": round(self.current, 2),
            "delta": round(self.delta, 2),
            "percent": None if self.percent is None else round(self.percent, 1),
        }


def movers(rows: Iterable[CostRow], limit: int | None = None) -> list[Change]:
    """Per-service change between the two most recent months, biggest swing first."""
    rows = list(rows)
    periods = sorted(monthly_totals(rows))
    if len(periods) < 2:
        return []

    previous_month, current_month = periods[-2], periods[-1]
    per_month: dict[tuple[str, str], float] = {}
    for row in rows:
        key = (row.service, row.month)
        per_month[key] = per_month.get(key, 0.0) + row.amount

    changes: list[Change] = []
    for service in sorted({row.service for row in rows}):
        previous = per_month.get((service, previous_month), 0.0)
        current = per_month.get((service, current_month), 0.0)
        if previous == 0.0 and current == 0.0:
            continue
        changes.append(
            Change(
                service=service,
                previous_month=previous_month,
                current_month=current_month,
                previous=previous,
                current=current,
            )
        )

    changes.sort(key=lambda change: abs(change.delta), reverse=True)
    return changes[:limit] if limit else changes


@dataclass(frozen=True)
class Spike:
    service: str
    month: str
    amount: float
    baseline: float

    @property
    def ratio(self) -> float:
        return self.amount / self.baseline if self.baseline else 0.0

    def as_dict(self) -> dict:
        return {
            "service": self.service,
            "month": self.month,
            "amount": round(self.amount, 2),
            "baseline": round(self.baseline, 2),
            "ratio": round(self.ratio, 2),
        }


def spikes(rows: Iterable[CostRow], factor: float = 2.0) -> list[Spike]:
    """Months where a service billed at least `factor` times its own median month."""
    series: dict[str, dict[str, float]] = {}
    for row in rows:
        months = series.setdefault(row.service, {})
        months[row.month] = months.get(row.month, 0.0) + row.amount

    found: list[Spike] = []
    for service, months in series.items():
        if len(months) < 3:
            continue
        baseline = median(months.values())
        if baseline <= 0:
            continue
        for month in sorted(months):
            amount = months[month]
            if amount > baseline and amount >= baseline * factor:
                found.append(Spike(service=service, month=month, amount=amount, baseline=baseline))

    found.sort(key=lambda spike: spike.ratio, reverse=True)
    return found


@dataclass(frozen=True)
class Waste:
    account: str
    service: str
    amount: float

    def as_dict(self) -> dict:
        return {
            "account": self.account,
            "service": self.service,
            "amount": round(self.amount, 2),
        }


def waste(rows: Iterable[CostRow]) -> list[Waste]:
    """Spend on resources that are marked idle, stopped or unused."""
    totals: dict[tuple[str, str], float] = {}
    for row in rows:
        if not row.idle:
            continue
        key = (row.account, row.service)
        totals[key] = totals.get(key, 0.0) + row.amount
    found = [Waste(account=account, service=service, amount=amount) for (account, service), amount in totals.items()]
    found.sort(key=lambda item: item.amount, reverse=True)
    return found


def concentration(rows: Iterable[CostRow]) -> float:
    """Share of total spend taken by the single most expensive service, between 0 and 1."""
    totals = service_totals(rows)
    total = sum(totals.values())
    if total <= 0 or not totals:
        return 0.0
    return next(iter(totals.values())) / total
