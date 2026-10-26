"""Command line entry point: summary, movers, spikes, waste, budget, report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cloud_spend_analyzer.analysis import concentration, movers, service_totals, spikes, waste
from cloud_spend_analyzer.budgets import load_budget
from cloud_spend_analyzer.models import CostError, ParsedCosts, parse_costs
from cloud_spend_analyzer.report import SpendReport, money


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CostError(f"cannot read {path}: {exc.strerror or exc}") from exc


def _load(path: str, source: str) -> tuple[SpendReport, ParsedCosts]:
    parsed = parse_costs(_read(path))
    return SpendReport(rows=parsed.rows, source=source, problems=parsed.problems), parsed


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloud-spend",
        description="Offline analysis of a cloud cost CSV export.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    summary = sub.add_parser("summary", help="monthly totals, top services and verdict")
    summary.add_argument("file")

    movers_cmd = sub.add_parser("movers", help="biggest service changes between the last two months")
    movers_cmd.add_argument("file")
    movers_cmd.add_argument("--limit", type=int, default=10)

    spikes_cmd = sub.add_parser("spikes", help="months far above a service's own median")
    spikes_cmd.add_argument("file")
    spikes_cmd.add_argument("--factor", type=float, default=2.0)

    waste_cmd = sub.add_parser("waste", help="spend on idle, stopped or unused resources")
    waste_cmd.add_argument("file")

    budget_cmd = sub.add_parser("budget", help="compare the export against budget limits")
    budget_cmd.add_argument("file")
    budget_cmd.add_argument("--budget", required=True, help="path to a budget JSON document")

    report_cmd = sub.add_parser("report", help="full report, text or JSON")
    report_cmd.add_argument("file")
    report_cmd.add_argument("--budget", help="path to a budget JSON document")
    report_cmd.add_argument("--factor", type=float, default=2.0)
    report_cmd.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        report, parsed = _load(args.file, Path(args.file).name)
    except CostError as exc:
        return _fail(str(exc))

    if args.command == "summary":
        totals = report.months
        print(f"rows      : {len(parsed.rows)}")
        print(f"accounts  : {len(parsed.accounts)}")
        print(f"services  : {len(parsed.services)}")
        print(f"total     : {money(report.total)}")
        print(f"concentration: {concentration(parsed.rows) * 100:.1f}% in the top service")
        print("months    :")
        for month, value in totals.items():
            print(f"  {month}  {money(value):>14}")
        print("top services:")
        for name, value in list(service_totals(parsed.rows).items())[:5]:
            print(f"  {name:<18}{money(value):>14}")
        return 0

    if args.command == "movers":
        changes = movers(parsed.rows, limit=args.limit)
        if not changes:
            print("need at least two months of data", file=sys.stderr)
            return 2
        print(f"{changes[0].previous_month} -> {changes[0].current_month}")
        for change in changes:
            percent = "new" if change.percent is None else f"{change.percent:+.1f}%"
            print(f"  {change.service:<18}{money(change.delta):>14}  {percent:>8}")
        return 0

    if args.command == "spikes":
        found = spikes(parsed.rows, factor=args.factor)
        if not found:
            print(f"no service billed more than {args.factor:g}x its median month")
            return 0
        for spike in found:
            print(
                f"  {spike.service:<18}{spike.month}  {money(spike.amount):>12} "
                f"= {spike.ratio:.1f}x median {money(spike.baseline)}"
            )
        return 0

    if args.command == "waste":
        found = waste(parsed.rows)
        if not found:
            print("no idle resources found")
            return 0
        for item in found:
            print(f"  {item.account:<18}{item.service:<16}{money(item.amount):>12}")
        print(f"total idle spend: {money(sum(item.amount for item in found))}")
        return 0

    budget_path = getattr(args, "budget", None)
    if budget_path:
        try:
            report.budget = load_budget(_read(budget_path))
        except CostError as exc:
            return _fail(str(exc))

    factor = getattr(args, "factor", None)
    if factor:
        report.spike_factor = factor

    if args.command == "budget":
        if report.budget is None:
            return _fail("--budget is required")
        if not report.breaches:
            print("every budget limit respected")
            return 0
        for breach in report.breaches:
            print(
                f"  {breach.month}  {breach.scope}:{breach.name:<16}{money(breach.actual):>12} "
                f"vs {money(breach.limit)}  +{breach.percent:.0f}%"
            )
        print(f"{len(report.breaches)} breach(es), {money(sum(b.over for b in report.breaches))} over budget")
        return 1

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.render())

    return 1 if report.health == "risk" else 0


if __name__ == "__main__":
    raise SystemExit(main())
