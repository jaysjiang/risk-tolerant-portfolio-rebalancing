# Data availability

The study uses a deliberately selected set of nine US sector ETFs. Historical prices were obtained from Yahoo Finance and checked against issuer/distributor corporate-action evidence. The underlying provider observations, distribution snapshots, daily portfolio ledgers and individual bootstrap draws are not redistributed in this repository.

## Sample and data review

Development covers 2005–2014 and remains provisional because nine September 2006 cash amounts are unresolved. Validation covers 2015–2019. The final evaluation trades from 2 January 2020 through 31 December 2025, with risk warmup from 2017. The unresolved 2006 events do not enter either reviewed evaluation window. A January 2026 calendar buffer schedules terminal orders; it supplies no future returns.

The price snapshots are retrospective and were not independently replicated in full. Data QA covered the historical sample before final strategy evaluation; policy selection was frozen before final-period strategy outcomes were computed.

## Exact-input replay

The public adapter requires these five original files in an external directory:

| File | Role |
|---|---|
| `input_opens.parquet` | Nominal opening execution prices |
| `input_closes.parquet` | Nominal closing valuation prices |
| `input_risk_returns.parquet` | Reviewed total returns for risk estimation |
| `input_calendar.json` | Session calendar including scheduling buffer |
| `input_actions.json` | Reviewed cash distributions and genuine splits |

The [replay contract](../reports/results/replay_contract.json) supplies their exact hashes, ETF order, evaluation dates and frozen source hashes. Replay requires all five files to match these hashes.

The snapshots are not included. A new replication can use an authorized data source with a documented adapter that checks price units, return adjustments, ex-dates and pay-dates. Different snapshots may produce different results. Redistribution remains subject to the provider's terms.

The public aggregate outputs and synthetic tests remain usable without private data. See [reproducibility](reproducibility.md).
