"""Assemble the aggregations into one printable report."""

from __future__ import annotations

from dataclasses import dataclass, field

from cloud_spend_analyzer import analysis
from cloud_spend_analyzer.budgets import Breach, Budget, check_budget
from cloud_spend_analyzer.models import CostRow


def money(value: float) -> str:
    return f"${value:,.2f}"


@dataclass
class SpendReport:
    rows: list[CostRow]
    budget: Budget | None = None
    spike_factor: float = 2.0
    source: str = "cloud costs"
    problems: list[str] = field(default_factory=list)

    @property
    def months(self) -> dict[str, float]:
        return analysis.monthly_totals(self.rows)

    @property
    def latest_month(self) -> str:
        return next(reversed(self.months), "")

    @property
    def latest_total(self) -> float:
        return self.months.get(self.latest_month, 0.0)

    @property
    def services(self) -> dict[str, float]:
        return analysis.service_totals(self.rows)

    @property
    def accounts(self) -> dict[str, float]:
        return analysis.account_totals(self.rows)

    @property
    def changes(self) -> list[analysis.Change]:
        return analysis.movers(self.rows)

    @property
    def spikes(self) -> list[analysis.Spike]:
        return analysis.spikes(self.rows, self.spike_factor)

    @property
    def waste(self) -> list[analysis.Waste]:
        return analysis.waste(self.rows)

    @property
    def breaches(self) -> list[Breach]:
        return check_budget(self.budget, self.rows) if self.budget else []

    @property
    def total(self) -> float:
        return sum(row.amount for row in self.rows)

    @property
    def waste_total(self) -> float:
        return sum(item.amount for item in self.waste)

    @property
    def waste_share(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.waste_total / self.total * 100.0

    @property
    def health(self) -> str:
        if any(breach.percent >= 25 for breach in self.breaches) or self.spikes:
            return "risk"
        if self.breaches or self.waste_share >= 20:
            return "watch"
        return "good"

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "months": {month: round(value, 2) for month, value in self.months.items()},
            "latest_month": self.latest_month,
            "latest_total": round(self.latest_total, 2),
            "total": round(self.total, 2),
            "services": {name: round(value, 2) for name, value in self.services.items()},
            "accounts": {name: round(value, 2) for name, value in self.accounts.items()},
            "concentration": round(analysis.concentration(self.rows) * 100, 1),
            "changes": [change.as_dict() for change in self.changes],
            "spikes": [spike.as_dict() for spike in self.spikes],
            "waste": [item.as_dict() for item in self.waste],
            "waste_total": round(self.waste_total, 2),
            "waste_share": round(self.waste_share, 1),
            "breaches": [breach.as_dict() for breach in self.breaches],
            "health": self.health,
            "problems": self.problems,
        }

    def render(self) -> str:
        lines = [
            f"{self.source}  -  {len(self.months)} month(s), {len(self.rows)} row(s), {len(self.services)} service(s)",
            f"total spend: {money(self.total)}   latest month: {self.latest_month} {money(self.latest_total)}",
            f"top service share: {analysis.concentration(self.rows) * 100:.1f}%   verdict: {self.health.upper()}",
            "",
            "Spend by month",
        ]
        for month, value in self.months.items():
            lines.append(f"  {month}  {money(value):>14}")

        lines += ["", "Top services"]
        for index, (name, value) in enumerate(self.services.items(), start=1):
            if index > 5:
                break
            share = value / self.total * 100 if self.total else 0.0
            lines.append(f"  {index}. {name:<18}{money(value):>14}  {share:5.1f}%")

        if self.changes:
            lines += ["", f"Biggest movers ({self.changes[0].previous_month} -> {self.changes[0].current_month})"]
            for change in self.changes[:5]:
                pct = "new" if change.percent is None else f"{change.percent:+.1f}%"
                lines.append(f"  {change.service:<18}{money(change.delta):>14}  {pct:>8}")

        if self.spikes:
            lines += ["", f"Spikes (at least {self.spike_factor:g}x the service median)"]
            for spike in self.spikes[:5]:
                lines.append(
                    f"  {spike.service:<18}{spike.month}  {money(spike.amount):>12} vs {money(spike.baseline)} baseline"
                )

        if self.waste:
            lines += ["", f"Idle spend  {money(self.waste_total)}  ({self.waste_share:.1f}% of total)"]
            for item in self.waste[:5]:
                lines.append(f"  {item.account:<18}{item.service:<16}{money(item.amount):>12}")

        if self.budget is not None:
            if self.breaches:
                lines += ["", f"Budget breaches ({len(self.breaches)})"]
                for breach in self.breaches[:5]:
                    lines.append(
                        f"  {breach.month}  {breach.scope}:{breach.name:<16} "
                        f"{money(breach.actual)} vs {money(breach.limit)}  +{breach.percent:.0f}%"
                    )
            else:
                lines += ["", "Budget: every limit respected"]

        if self.problems:
            lines += ["", f"Skipped {len(self.problems)} row(s)"]
            lines += [f"  {problem}" for problem in self.problems[:5]]

        return "\n".join(lines)
