# Cloud-Spend-Analyzer

[![CI](https://github.com/abubakarsiddique360/Cloud-Spend-Analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/abubakarsiddique360/Cloud-Spend-Analyzer/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![dependencies](https://img.shields.io/badge/dependencies-none-success)

Give it a cloud cost export and it answers the five questions people actually ask in a
FinOps review: what did we spend, which service moved, did anything spike, what is idle,
and are we over budget. Standard library only, no cloud credentials, no network calls.

## Why it exists

Cloud consoles show a bill. They are much worse at telling you *why* the bill changed.
The raw CSV export already contains the answer, but only after grouping, differencing and
baselining, which is exactly the friction that stops people from looking. This tool does that
work in one command and prints a verdict you can paste into a ticket.

## Install

```bash
pip install -e .
```

Python 3.10+, zero runtime dependencies.

## Usage

```bash
cloud-spend summary costs.csv                     # totals, top services, concentration
cloud-spend movers  costs.csv --limit 5           # service changes between the last two months
cloud-spend spikes  costs.csv --factor 2          # months far above a service's own median
cloud-spend waste   costs.csv                     # spend marked idle, stopped or unused
cloud-spend budget  costs.csv --budget budget.json
cloud-spend report  costs.csv --budget budget.json --json
```

Every command takes the same CSV. Exit codes: `0` healthy, `1` budget breach or `RISK`
verdict, `2` unreadable or invalid input, so a scheduled job can fail loudly.

### Input format

```csv
month,account,service,amount,state
2025-03,prod-data,Compute,9800.00,running
2025-03,sandbox,Storage,300.00,stopped
```

- `month` must be `YYYY-MM`.
- `amount` may contain `$`, thousands separators and underscores.
- `state` is optional and defaults to `running`; `idle`, `stopped` and `unused` count as waste.
- Extra columns are ignored. Broken rows are skipped and listed in the report instead of
  killing the whole run, and a file with no usable rows is a hard error.

### Budget format

```json
{
  "monthly": 20000,
  "per_service": { "Compute": 6000, "Database": 1600 },
  "per_account": { "prod-data": 12500, "sandbox": 2000 }
}
```

Limits are per month. Unknown keys are rejected so a typo such as `per_services` never
silently disables a limit.

## Example report

```text
cloud-spend.csv  -  4 month(s), 33 row(s), 5 service(s)
total spend: $57,475.00   latest month: 2025-04 $21,685.00
top service share: 72.5%   verdict: RISK

Spend by month
  2025-01      $10,930.00
  2025-02      $11,270.00
  2025-03      $13,590.00
  2025-04      $21,685.00

Top services
  1. Compute               $41,680.00   72.5%
  2. Database               $6,235.00   10.8%

Biggest movers (2025-03 -> 2025-04)
  Compute                $8,000.00    +84.7%
  Storage                   $45.00     +2.7%

Spikes (at least 2x the service median)
  Compute           2025-04    $17,440.00 vs $8,470.00 baseline

Idle spend  $8,270.00  (14.4% of total)
  sandbox           Compute            $5,800.00

Budget breaches (8)
  2025-04  service:Compute          $17,440.00 vs $6,000.00  +191%
```

## How the numbers are produced

| Concept | Definition |
| --- | --- |
| Monthly total | Sum of `amount` per month, oldest first. |
| Top service share | Spend of the largest service divided by all spend. Above ~60% is concentration risk. |
| Mover | `current - previous` for each service across the two most recent months, ranked by absolute size. `percent` is `null` for a brand new service. |
| Spike | A month where a service bills at least `factor` times its own **median** month. Median, not mean, so one bad month cannot hide itself. Needs three months of history. |
| Waste | Spend whose `state` is `idle`, `stopped` or `unused`. |
| Verdict | `risk` if any spike exists or a limit is exceeded by 25% or more, `watch` if there is any breach or idle spend is 20% of total, otherwise `good`. |

## Design notes

- **Aggregation is pure.** `analysis.py` takes a list of rows and returns plain numbers and
  frozen dataclasses, so every function is trivially testable and reusable in a notebook.
- **The report owns no state.** `SpendReport` is a thin view that recomputes properties from
  the rows, which keeps CLI output and JSON output guaranteed consistent.
- **Median baselines instead of moving averages**, because a single runaway month should be
  flagged immediately rather than averaged away.
- **Every number is rounded once**, at serialisation time, so text and JSON never disagree.

## Project layout

```text
src/cloud_spend_analyzer/
  models.py    CSV parsing, row validation, idle detection
  analysis.py  monthly/service/account totals, movers, spikes, waste, concentration
  budgets.py   budget JSON loading and breach detection
  report.py    SpendReport, verdict, text and JSON rendering
  cli.py       summary / movers / spikes / waste / budget / report
data/
  cloud-spend.csv   33-row sample export, four months, three accounts
  budget.json        sample limits that the sample data breaches
tests/              57 tests covering parsing, analysis, budgets and the CLI
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

CI runs the suite on Python 3.10 and 3.12, checks formatting, then runs the tool against the
sample data so the documented output cannot drift.

## Limitations

- The CSV must be a flat, single-currency export; currency conversion is out of scope.
- Negative amounts (credits, refunds) are summed as-is and can push a service below a zero
  baseline, in which case that service is skipped by spike detection.
- Spikes need at least three months of data for one service; two points are not a trend.
- The tool never contacts a cloud provider, so it cannot attribute cost to tags that are not
  already columns in the export.

## License

MIT, copyright (c) 2026 ABU BAKAR SIDDIQUE.
