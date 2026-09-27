# Forecast-Risk Tolerance and Portfolio Rebalancing

A Python study of partial rebalancing in nine US sector ETFs. The policy minimizes trading while keeping forecast volatility within 2% of the constrained minimum. The study compares this rule with calendar, weight-band and variance-penalty policies using a common holdings and transaction-cost model.

[Research note (PDF)](PDF/research_note.pdf) · [Research note (Markdown)](reports/research_note.md) · [Full results](reports/final_evaluation.md) · [Mechanism and failure checks](reports/mechanism_review.md)

## Main result

The primary comparator was selected on 2015–2019 validation data and frozen before the 2020–2025 evaluation. It is a conventional variance-plus-turnover penalty policy with penalty 0.3.

| 2020–2025 evaluation | Risk-tolerance policy | Frozen comparator |
|---|---:|---:|
| Annualized gross volatility | 17.53% | 17.43% |
| Annual full-notional turnover | 0.776 | 1.189 |
| Annual routine cost debit, bp/NAV | 3.88 | 5.95 |
| Net CAGR | 8.42% | 8.79% |

Turnover falls **34.8%**, while realized volatility increases by **0.102 percentage points**. At an assumed cost of 5 basis points per dollar bought or sold, the saving is **2.07 basis points per year**. Turnover counts purchases plus sales and excludes initial entry; net wealth includes entry costs.

The paired stationary bootstrap gives a volatility ratio of 1.0058 (95% interval 0.999988–1.014907) and a turnover ratio of 0.6524 (0.5332–0.7555). These meet the prespecified joint practical criterion under the bootstrap assumptions. Net CAGR is lower for the proposed policy.

![Realized risk and turnover across all frozen baseline policies](reports/figures/publication_risk_turnover.png)

## Research design

- **Universe:** XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV and XLY; long only, fully invested ETF sleeve, 25% target-weight cap.
- **Risk model:** trailing 252-session Ledoit–Wolf covariance in the baseline.
- **Implementation:** after-close signals, next-open target execution, actual drifted holdings, self-financing costs, cash-dividend receivables and genuine splits.
- **Comparisons:** 21 fixed policy settings across nine prespecified scenarios; 189 final runs. Calendar, partial weight-band and variance-penalty policies share accounting and cost conventions.
- **Inference:** 5,000 paired stationary-bootstrap replications; predefined thresholds and sensitivity checks. No final-period parameter selection.

The optimizer, holdings engine, policy rules and inference code are in [src/risk_rebalancing](src/risk_rebalancing). The [research protocol](docs/research_protocol.md) and [final evaluation specification](docs/final_evaluation_specification.md) record the design.

## Run without market data

Use Python 3.12; the original research environment used 3.12.14. From this repository root:

```shell
python -m venv .venv
```

Activate the environment (`.venv\Scripts\Activate.ps1` in PowerShell, or `source .venv/bin/activate` on macOS/Linux), then:

```shell
python -m pip install -r requirements.txt
python -m pip install --no-deps --no-build-isolation -e .
python scripts/reproduce.py check
python scripts/reproduce.py demo --workers 2
```

`check` runs the public regression suite, verifies release checksums and local links, and checks the aggregate result grid. `demo` exercises five policies on a deterministic artificial market containing cash, in-kind and split events. Its returns are synthetic. New outputs go into unique folders under ignored `work/`.

## Financial reproduction and data availability

Provider snapshots and daily financial ledgers are excluded. The public repository contains the scientific source, reports, figures, all 189 aggregate metric rows, bootstrap summaries and frozen selection metadata. Public tests can run without obtaining data.

Financial replay requires the five exact reviewed input snapshots identified by SHA-256 in the [replay contract](reports/results/replay_contract.json):

```shell
python scripts/reproduce.py smoke --data-dir "PATH_TO_REVIEWED_INPUTS"
python scripts/reproduce.py full --data-dir "PATH_TO_REVIEWED_INPUTS" --workers 8
```

The smoke run covers the first 15 sessions of the frozen primary pair. The full command runs all 189 configurations and compares every aggregate metric, all 11 bootstrap interval summaries, classifications and resampling-index checksums. See [data availability](docs/data_availability.md) and [reproducibility scope](docs/reproducibility.md).

## Limitations

- Monthly minimum-variance rebalancing is a less conclusive comparison: the volatility-ratio upper bound exceeds the 1.02 threshold. The result depends on the comparator.
- The 126-session estimation window misses the turnover confidence threshold, and 2020 alone misses the point turnover target.
- The large saving with two-session execution delay depends on a FIFO queue that ignores pending targets. It is not evidence of general robustness to latency.
- Nine unresolved September 2006 cash amounts affect provisional development only. They do not enter the reviewed validation or final windows. Prices are retrospective snapshots and were not independently replicated in full.
- Fractional shares, opening-price sizing and linear costs are assumptions. The study does not establish alpha, execution capacity or live profitability.

## Repository guide

| Location | Contents |
|---|---|
| [src/risk_rebalancing](src/risk_rebalancing) | Risk estimation, optimization, accounting and inference |
| [tests](tests) | Data-free optimizer, ledger, policy, selection and inference checks |
| [scripts](scripts) | Tests, synthetic data and financial replay commands |
| [docs](docs) | Method specifications, data status and reproduction instructions |
| [reports/results](reports/results) | Aggregate results, frozen configuration and provenance |
| [PDF/research_note.pdf](PDF/research_note.pdf) | Six-page research note |

Jay (Shijie) Jiang · September 2026
