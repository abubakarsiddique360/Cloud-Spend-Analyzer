from __future__ import annotations

from pathlib import Path

import pytest

HEADER = "month,account,service,amount,state\n"

SIMPLE = HEADER + (
    "2025-01,prod,Compute,100.00,running\n"
    "2025-01,prod,Storage,40.00,running\n"
    "2025-02,prod,Compute,150.00,running\n"
    "2025-02,prod,Storage,40.00,idle\n"
)


@pytest.fixture
def cost_file(tmp_path: Path):
    def write(body: str = SIMPLE, name: str = "costs.csv") -> Path:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        return path

    return write


@pytest.fixture
def sample_csv() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "cloud-spend.csv"


@pytest.fixture
def sample_budget() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "budget.json"
