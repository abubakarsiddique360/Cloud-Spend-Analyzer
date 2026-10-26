"""Read and validate cloud cost rows from CSV text."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
REQUIRED_COLUMNS = ("month", "account", "service", "amount")
IDLE_STATES = frozenset({"idle", "stopped", "unused"})


class CostError(ValueError):
    """Raised when a cost export cannot be interpreted."""


def parse_amount(raw: str) -> float:
    text = raw.strip().replace("$", "").replace(",", "").replace("_", "")
    if not text:
        raise CostError("amount is empty")
    try:
        return float(text)
    except ValueError as exc:
        raise CostError(f"amount is not a number: {raw!r}") from exc


@dataclass(frozen=True)
class CostRow:
    month: str
    account: str
    service: str
    amount: float
    state: str = "running"

    @property
    def idle(self) -> bool:
        return self.state.strip().lower() in IDLE_STATES

    def as_dict(self) -> dict:
        return {
            "month": self.month,
            "account": self.account,
            "service": self.service,
            "amount": round(self.amount, 2),
            "state": self.state,
        }


@dataclass
class ParsedCosts:
    rows: list[CostRow] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def accounts(self) -> list[str]:
        return sorted({row.account for row in self.rows})

    @property
    def services(self) -> list[str]:
        return sorted({row.service for row in self.rows})

    @property
    def months(self) -> list[str]:
        return sorted({row.month for row in self.rows})


def _normalise_header(names: list[str | None]) -> list[str]:
    return [(name or "").strip().lower() for name in names]


def _cell(raw: list[str], index: dict[str, int], column: str) -> str:
    position = index[column]
    return raw[position].strip() if position < len(raw) else ""


def parse_costs(text: str) -> ParsedCosts:
    if not text.strip():
        raise CostError("the cost file is empty")

    reader = csv.reader(io.StringIO(text))
    try:
        header = _normalise_header(next(reader))
    except StopIteration as exc:
        raise CostError("the cost file is empty") from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise CostError(f"missing column(s): {', '.join(missing)}")

    index = {name: position for position, name in enumerate(header) if name}
    state_index = index.get("state")
    parsed = ParsedCosts()

    for line_number, raw in enumerate(reader, start=2):
        if not raw or not any(value.strip() for value in raw):
            continue

        month = _cell(raw, index, "month")
        account = _cell(raw, index, "account")
        service = _cell(raw, index, "service")
        if not MONTH_RE.match(month):
            parsed.problems.append(f"line {line_number}: month is not YYYY-MM: {month!r}")
            continue
        if not account or not service:
            parsed.problems.append(f"line {line_number}: account and service are required")
            continue
        try:
            amount = parse_amount(_cell(raw, index, "amount"))
        except CostError as exc:
            parsed.problems.append(f"line {line_number}: {exc}")
            continue

        state = "running"
        if state_index is not None and state_index < len(raw) and raw[state_index].strip():
            state = raw[state_index].strip()

        parsed.rows.append(CostRow(month=month, account=account, service=service, amount=amount, state=state))

    if not parsed.rows:
        raise CostError("no usable cost rows were found")
    return parsed
