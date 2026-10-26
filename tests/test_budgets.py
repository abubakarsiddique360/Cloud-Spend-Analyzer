from __future__ import annotations

import pytest

from cloud_spend_analyzer.budgets import Budget, check_budget, load_budget
from cloud_spend_analyzer.models import CostError, CostRow

ROWS = [
    CostRow("2025-01", "prod", "Compute", 600.0),
    CostRow("2025-01", "prod", "Database", 500.0),
    CostRow("2025-02", "prod", "Compute", 400.0),
]


def test_load_full_budget() -> None:
    budget = load_budget('{"monthly": 1000, "per_service": {"Compute": 500}, "per_account": {"prod": 900}}')
    assert budget.monthly == 1000.0
    assert budget.per_service == {"Compute": 500.0}
    assert budget.per_account == {"prod": 900.0}
    assert budget.empty is False


def test_load_budget_from_dict() -> None:
    assert load_budget({"monthly": 10}).monthly == 10.0


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(CostError, match="unknown budget key"):
        load_budget({"monthly_budget": 10})


def test_broken_json_is_rejected() -> None:
    with pytest.raises(CostError, match="not valid JSON"):
        load_budget("{oops}")


def test_non_object_is_rejected() -> None:
    with pytest.raises(CostError, match="must be a JSON object"):
        load_budget("[1, 2]")


@pytest.mark.parametrize("payload", [{"monthly": "1000"}, {"monthly": True}, {"per_service": {"x": "9"}}])
def test_non_numeric_limits_are_rejected(payload) -> None:
    with pytest.raises(CostError, match="must be a number"):
        load_budget(payload)


def test_non_positive_limits_are_rejected() -> None:
    with pytest.raises(CostError, match="greater than zero"):
        load_budget({"monthly": 0})
    with pytest.raises(CostError, match="greater than zero"):
        load_budget({"per_service": {"Compute": -1}})


def test_empty_budget_is_rejected() -> None:
    with pytest.raises(CostError, match="no limits"):
        load_budget({})


def test_monthly_breach_is_per_month() -> None:
    breaches = check_budget(Budget(monthly=700), ROWS)
    assert [(breach.month, breach.actual) for breach in breaches] == [("2025-01", 1100.0)]
    assert breaches[0].over == 400.0
    assert breaches[0].percent == pytest.approx(400 / 700 * 100)


def test_service_breach() -> None:
    breaches = check_budget(Budget(per_service={"Compute": 500}), ROWS)
    assert len(breaches) == 1
    assert breaches[0].scope == "service"
    assert breaches[0].name == "Compute"
    assert breaches[0].month == "2025-01"


def test_account_breach() -> None:
    breaches = check_budget(Budget(per_account={"prod": 1000}), ROWS)
    assert [(breach.month, breach.over) for breach in breaches] == [("2025-01", 100.0)]


def test_no_breach_when_limits_are_generous() -> None:
    assert check_budget(Budget(monthly=5000, per_service={"Compute": 5000}), ROWS) == []


def test_breaches_are_sorted_by_overspend() -> None:
    breaches = check_budget(Budget(monthly=100, per_service={"Compute": 10}), ROWS)
    assert breaches[0].over >= breaches[-1].over


def test_breach_as_dict() -> None:
    breach = check_budget(Budget(monthly=700), ROWS)[0]
    payload = breach.as_dict()
    assert payload["scope"] == "monthly"
    assert payload["limit"] == 700.0
    assert payload["over"] == 400.0
