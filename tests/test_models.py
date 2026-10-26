from __future__ import annotations

import pytest

from cloud_spend_analyzer.models import CostError, CostRow, parse_amount, parse_costs


def test_parse_rows_and_shape() -> None:
    parsed = parse_costs("Month,Account,Service,Amount\n2025-01,prod,Compute,100\n2025-02,prod,Compute,120\n")
    assert len(parsed.rows) == 2
    assert parsed.problems == []
    assert parsed.rows[0] == CostRow("2025-01", "prod", "Compute", 100.0)
    assert parsed.months == ["2025-01", "2025-02"]
    assert parsed.accounts == ["prod"]
    assert parsed.services == ["Compute"]


def test_amount_accepts_currency_formatting() -> None:
    assert parse_amount(" $1,234.50 ") == 1234.5
    assert parse_amount("12_000") == 12000.0


def test_amount_rejects_garbage() -> None:
    with pytest.raises(CostError):
        parse_amount("n/a")
    with pytest.raises(CostError):
        parse_amount("   ")


def test_missing_column_is_fatal() -> None:
    with pytest.raises(CostError, match="missing column"):
        parse_costs("month,account,service\n2025-01,prod,Compute\n")


def test_empty_file_is_fatal() -> None:
    with pytest.raises(CostError):
        parse_costs("   \n")


def test_rows_without_data_are_fatal() -> None:
    with pytest.raises(CostError, match="no usable"):
        parse_costs("month,account,service,amount\n")


def test_bad_month_is_reported_and_skipped() -> None:
    parsed = parse_costs("month,account,service,amount\n2025-13,prod,Compute,10\n2025-01,prod,Compute,10\n")
    assert len(parsed.rows) == 1
    assert "month is not YYYY-MM" in parsed.problems[0]


def test_bad_amount_is_reported_and_skipped() -> None:
    parsed = parse_costs("month,account,service,amount\n2025-01,prod,Compute,ten\n2025-01,prod,Compute,10\n")
    assert len(parsed.rows) == 1
    assert "not a number" in parsed.problems[0]


def test_missing_identity_is_reported() -> None:
    parsed = parse_costs("month,account,service,amount\n2025-01,,Compute,10\n2025-01,prod,Compute,10\n")
    assert len(parsed.rows) == 1
    assert "required" in parsed.problems[0]


def test_state_defaults_and_idle_detection() -> None:
    parsed = parse_costs(
        "month,account,service,amount,state\n"
        "2025-01,prod,Compute,10,STOPPED\n"
        "2025-01,prod,Storage,10,\n"
        "2025-01,prod,CDN,10,running\n"
    )
    assert parsed.rows[0].idle is True
    assert parsed.rows[1].state == "running"
    assert parsed.rows[1].idle is False
    assert parsed.rows[2].idle is False


def test_blank_lines_are_skipped() -> None:
    parsed = parse_costs("month,account,service,amount\n\n2025-01,prod,Compute,10\n\n")
    assert len(parsed.rows) == 1


def test_row_as_dict_rounds() -> None:
    row = CostRow("2025-01", "prod", "Compute", 10.0059, "idle")
    assert row.as_dict()["amount"] == 10.01
    assert row.as_dict()["state"] == "idle"
