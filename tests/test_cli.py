from __future__ import annotations

import json

from cloud_spend_analyzer.cli import main


def test_summary(cost_file, capsys) -> None:
    assert main(["summary", str(cost_file())]) == 0
    out = capsys.readouterr().out
    assert "rows      : 4" in out
    assert "total     : $330.00" in out
    assert "2025-02" in out


def test_movers(cost_file, capsys) -> None:
    assert main(["movers", str(cost_file())]) == 0
    out = capsys.readouterr().out
    assert "2025-01 -> 2025-02" in out
    assert "Compute" in out


def test_movers_needs_two_months(cost_file, capsys) -> None:
    body = "month,account,service,amount\n2025-01,prod,Compute,10\n"
    assert main(["movers", str(cost_file(body))]) == 2
    assert "at least two months" in capsys.readouterr().err


def test_spikes_empty(cost_file, capsys) -> None:
    assert main(["spikes", str(cost_file())]) == 0
    assert "no service billed" in capsys.readouterr().out


def test_spikes_found(cost_file, capsys) -> None:
    body = (
        "month,account,service,amount\n2025-01,prod,Compute,100\n2025-02,prod,Compute,100\n2025-03,prod,Compute,500\n"
    )
    assert main(["spikes", str(cost_file(body))]) == 0
    assert "5.0x median" in capsys.readouterr().out


def test_waste(cost_file, capsys) -> None:
    assert main(["waste", str(cost_file())]) == 0
    out = capsys.readouterr().out
    assert "total idle spend: $40.00" in out


def test_waste_when_clean(cost_file, capsys) -> None:
    body = "month,account,service,amount,state\n2025-01,prod,Compute,10,running\n"
    assert main(["waste", str(cost_file(body))]) == 0
    assert "no idle resources" in capsys.readouterr().out


def test_budget_respected(cost_file, sample_budget, capsys) -> None:
    body = "month,account,service,amount\n2025-01,prod,Compute,10\n"
    code = main(["budget", str(cost_file(body)), "--budget", str(sample_budget)])
    assert code == 0
    assert "every budget limit respected" in capsys.readouterr().out


def test_budget_breach(cost_file, tmp_path, capsys) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text('{"monthly": 50}', encoding="utf-8")
    assert main(["budget", str(cost_file()), "--budget", str(budget)]) == 1
    out = capsys.readouterr().out
    assert "breach(es)" in out


def test_budget_broken_json(cost_file, tmp_path, capsys) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text("{nope}", encoding="utf-8")
    assert main(["budget", str(cost_file()), "--budget", str(budget)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_report_text(cost_file, capsys) -> None:
    assert main(["report", str(cost_file())]) == 0
    out = capsys.readouterr().out
    assert "Spend by month" in out
    assert "Top services" in out
    assert "verdict" in out


def test_report_json(cost_file, capsys) -> None:
    main(["report", str(cost_file()), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 330.0
    assert payload["latest_month"] == "2025-02"
    assert payload["health"] == "good"
    assert isinstance(payload["changes"], list)


def test_report_with_budget_and_sample_data(sample_csv, sample_budget, capsys) -> None:
    code = main(["report", str(sample_csv), "--budget", str(sample_budget)])
    out = capsys.readouterr().out
    assert code == 1
    assert "Budget breaches" in out
    assert "Idle spend" in out


def test_report_sample_json(sample_csv, capsys) -> None:
    main(["report", str(sample_csv), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["latest_month"] == "2025-04"
    assert payload["spikes"]
    assert payload["waste_total"] > 0


def test_missing_file(tmp_path, capsys) -> None:
    assert main(["summary", str(tmp_path / "nope.csv")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_broken_csv(cost_file, capsys) -> None:
    assert main(["summary", str(cost_file("month,account\n2025-01,prod\n"))]) == 2
    assert "missing column" in capsys.readouterr().err
