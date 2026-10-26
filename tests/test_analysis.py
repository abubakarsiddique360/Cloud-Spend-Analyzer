from __future__ import annotations

from cloud_spend_analyzer.analysis import (
    account_totals,
    concentration,
    monthly_totals,
    movers,
    service_totals,
    spikes,
    waste,
)
from cloud_spend_analyzer.models import CostRow

ROWS = [
    CostRow("2025-01", "prod", "Compute", 100.0),
    CostRow("2025-01", "prod", "Storage", 40.0),
    CostRow("2025-01", "sandbox", "Compute", 20.0, "idle"),
    CostRow("2025-02", "prod", "Compute", 160.0),
    CostRow("2025-02", "prod", "Storage", 40.0),
    CostRow("2025-02", "sandbox", "Compute", 20.0, "idle"),
]


def test_monthly_totals_are_ordered() -> None:
    assert monthly_totals(ROWS) == {"2025-01": 160.0, "2025-02": 220.0}


def test_service_and_account_totals_are_largest_first() -> None:
    assert list(service_totals(ROWS)) == ["Compute", "Storage"]
    assert service_totals(ROWS)["Compute"] == 300.0
    assert account_totals(ROWS)["prod"] == 340.0


def test_movers_need_two_months() -> None:
    assert movers(ROWS[:3]) == []


def test_movers_rank_by_absolute_change() -> None:
    changes = movers(ROWS)
    assert changes[0].service == "Compute"
    assert changes[0].delta == 60.0
    assert changes[0].percent == 50.0
    assert changes[0].current_month == "2025-02"


def test_movers_report_new_services_without_percent() -> None:
    rows = [CostRow("2025-01", "prod", "Compute", 10.0), CostRow("2025-02", "prod", "CDN", 5.0)]
    changes = {change.service: change for change in movers(rows)}
    assert changes["CDN"].percent is None
    assert changes["CDN"].as_dict()["percent"] is None
    assert changes["Compute"].delta == -10.0


def test_movers_limit() -> None:
    assert len(movers(ROWS, limit=1)) == 1


def test_spikes_need_three_months() -> None:
    assert spikes(ROWS) == []


def test_spikes_find_the_outlier_month() -> None:
    rows = [
        CostRow("2025-01", "prod", "Compute", 100.0),
        CostRow("2025-02", "prod", "Compute", 110.0),
        CostRow("2025-03", "prod", "Compute", 900.0),
    ]
    found = spikes(rows)
    assert len(found) == 1
    assert found[0].month == "2025-03"
    assert found[0].baseline == 110.0
    assert found[0].ratio > 8


def test_spikes_respect_the_factor() -> None:
    rows = [
        CostRow("2025-01", "prod", "Compute", 100.0),
        CostRow("2025-02", "prod", "Compute", 100.0),
        CostRow("2025-03", "prod", "Compute", 260.0),
    ]
    assert spikes(rows, factor=2.0) != []
    assert spikes(rows, factor=3.0) == []


def test_waste_aggregates_idle_spend() -> None:
    found = waste(ROWS)
    assert len(found) == 1
    assert found[0].account == "sandbox"
    assert found[0].amount == 40.0


def test_waste_ignores_running_resources() -> None:
    assert waste([row for row in ROWS if not row.idle]) == []


def test_waste_ignores_other_states() -> None:
    rows = [CostRow("2025-01", "prod", "Compute", 10.0, "terminated")]
    assert waste(rows) == []


def test_concentration() -> None:
    assert concentration(ROWS) == 300.0 / 380.0
    assert concentration([]) == 0.0
    assert concentration([CostRow("2025-01", "p", "Zero", 0.0)]) == 0.0
