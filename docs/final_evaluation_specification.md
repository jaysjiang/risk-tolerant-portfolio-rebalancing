# Final evaluation specification

Implementation record, 27 September 2026 (Hong Kong), before final-test strategy
outcomes. Implements research-protocol sections 8–11 without changing policy
definitions, selected parameters, numerical tolerances or accounting conventions.

## Scope and frozen inputs

Trade 2020-01-02 through 2025-12-31, 1,508 sessions, resetting to USD 1 million
cash and the common initial equal-weight purchase. Risk history starts in 2017,
providing 754 prior sessions, sufficient for the longest 504-return window.
Only the last requested window is used at each close. No prior entitlements are
inherited. No provisional substitution is needed. Global development quarantine
remains unchanged. The new scope-specific release binds the bounded data checks,
original manifests, this specification, adapter and existing selection checksum.

Extend scheduling information only through 2026-01-09 using the installed XNYS
exchange calendar, requiring exact agreement with the cached overlapping dates.
No 2026 quotes/returns enter the tape; pending signals remain unfilled at the end.
Review the five genuine 2:1 splits on 2025-12-05 (XLB, XLE, XLK, XLU, XLY): nominal
shares double before opening trades; nominal share prices and dividend units
remain separate. Reconstruct risk returns with the share multiplier and cash per
new share. All positive cash amounts require valid issuer/adjudicated pay dates.

The saved validation freeze fixes A = risk_tolerant_0.02, B = variance_penalty_0.3,
band comparator = weight_band_0.08 (matched on validation), and penalty comparator
= variance_penalty_1 (unmatched). Verify the saved freeze and archived run, rather
than selecting again. Require risk.py, optimization.py, policies.py, ledger.py
and selection.py to match the frozen source hashes. Only orchestration/reporting
and a final-test scope label are added to the generic experiment runner.

## Scenarios fixed before opening outcomes

Run every original grid policy in each row, in original order (189 policy runs).
Each row starts fresh. These are one-at-a-time checks, not a Cartesian product.

| ID | Cost bp | Window | Estimator | Fill lag |
|---|---:|---:|---|---:|
| baseline | 5 | 252 | Ledoit–Wolf | 1 |
| cost_0 | 0 | 252 | Ledoit–Wolf | 1 |
| cost_1 | 1 | 252 | Ledoit–Wolf | 1 |
| cost_10 | 10 | 252 | Ledoit–Wolf | 1 |
| window_126 | 5 | 126 | Ledoit–Wolf | 1 |
| window_504 | 5 | 504 | Ledoit–Wolf | 1 |
| sample_covariance | 5 | 252 | Sample | 1 |
| diagonal_covariance | 5 | 252 | Diagonalized Ledoit–Wolf | 1 |
| extra_execution_lag | 5 | 252 | Ledoit–Wolf | 2 |

No epsilon, band, penalty, cap, failure-recovery rule or comparator is retuned.
The diagonal check alters targets and triggers together; it is not a causal
isolation of the no-trade region's geometry.

## Paired inference

For A/B, resample the aligned vector (gross return A, gross return B, routine
turnover A, routine turnover B). A stationary bootstrap starts uniformly, then
continues to the next circular date with probability 1-1/L or restarts uniformly
with probability 1/L. Discrete block lengths are geometric with expectation L.
This follows the [arch reference sampler](https://github.com/bashtage/arch/blob/main/arch/bootstrap/_samplers_python.py)
and [stationary-bootstrap documentation](https://bashtage.github.io/arch/bootstrap/generated/arch.bootstrap.StationaryBootstrap.html).

Use NumPy PCG64 seeded with 20260926, 5,000 replications, expected block length 20;
also report 10 and 60 for the baseline. Cost and model/lag rows receive the same
5,000-replication, L=20 paired analysis, labelled sensitivity evidence, with no
joint significance claim across scenarios. Generate all index rows in one fixed
order; batching metric calculations must not alter the random index stream.
Save draw-level ratio results and an index-array checksum. Never independently
resample policies, refit models, or regenerate paths inside bootstrap samples.

Ratios use sample standard deviations (ddof=1) and mean daily turnover; common
annualization cancels. Quantiles use linear interpolation. The 2.5th/97.5th
percentiles give each ordinary 95% interval and the corresponding Bonferroni
97.5% one-sided bounds for the two primary inequalities. Require both upper
bounds <= their thresholds (risk 1.02, turnover 0.80) for strong support.
Otherwise use the protocol's point-estimate classification. Also report the
separate evidence-against flag if either lower bound exceeds its threshold.
If any point denominator or bootstrap ratio is undefined, retain null outcomes
and counts and withhold significance; never drop bad draws silently.

Show each test year, fixed blocks 2020–2021, 2022–2023, 2024–2025, and each
leave-one-year-out ratio from the original continuous ledger, without resetting
holdings. These are descriptive stability checks. Bootstrap intervals rely on
time-series assumptions, condition on frozen policies, and do not remove regime
change, selection bias, data error or execution-model limitations.

## Diagnostics and examples

Summarize every baseline policy's realized risk/turnover/cost/net outcome, KEEP
and no-discretionary-trade frequency, concentration, cash exposure, cap repairs,
decision-time forecast ratios, execution-time ratios under the signal covariance,
solver status qualifications and independent checks. Report target compliance
separately from intervening drift and the delayed signal queue. Measure epsilon-zero
differences from daily MV.

For A, show the earliest executed KEEP instruction; earliest TARGET with positive
L1 trade and L1 distance strictly below the full daily-MV target by >1e-7; and
largest routine actual trade by notional/pre-trade NAV (ties: earliest date/log
order). Reconstruct the dated MV target only to identify/illustrate the partial
decision, using that day's recorded window. If absent, report absence. Use these rules
for all reported examples. Record current,
chosen and full-MV weights, risk ratios, next-open fill, and costs.

## Verification, storage and failures

Use exclusive study/run folders and a pre-launch source archive including tests
and fixtures. Preserve every failed attempt. Verify original financial hashes,
selection checksum, source hashes, all 189 configurations, 1,508 sessions each,
return/NAV reconciliation, charged-cost/turnover equality, genuine split events,
and stored artifact hashes. Recompute metrics from saved ledgers before analysis.
Write inference, stability tables, diagnostics, examples, all-grid tables,
figures and a readable final-evaluation report. Disclose any post-opening bug fix and repeat all affected runs.
Keep the statistical thresholds fixed and report failed configurations.
