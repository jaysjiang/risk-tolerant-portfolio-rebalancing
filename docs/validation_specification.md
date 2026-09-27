# Validation and comparator selection

Specification dated 27 September 2026 (Hong Kong), recorded before computing
2015-2019 strategy outcomes. Selection follows research-protocol section 7.

## Data scope and release

Validation is 2015-01-02 through 2019-12-31 (1,258 exchange sessions). Risk inputs
are bounded to 2013-01-01 through 2019-12-31, providing at least 504 complete
pre-entry sessions. Calendar-only scheduling information extends to 2020-01-09;
no 2020 prices or returns enter this tape. Holdings reset to USD 1 million cash
and buy equal weights at the first open. No pre-entry entitlements are inherited.

The nine unresolved 2006 cash amounts are outside this scope. No provisional
overlay, filling, date deletion or replacement return is used. The global audit
and strict development release remain quarantined. A separate explicit
`validation_data_release.json` binds this scope to the original manifests, audit,
protocol, this specification and adapter. Integrity checks still cover every
original source/table. Bounded data must have complete finite risk returns and
nominal quotes, no unresolved cash, consistent return reconstruction, and an
adjudicated payment/action schedule. Integrity is not independent confirmation
of every vendor price; the earlier source-quality limitations remain.

## XLF/XLRE mapping

On 2016-09-19, pre-open XLF holdings acquire 0.139146 XLRE shares per XLF share.
XLF share count does not change. The entitlement is marked at cached nominal XLRE
open/close prices, delivered after the 2016-09-22 close, and sold at the
2016-09-23 open. Both sale and ETF reinvestment pay the common 5 bp cost. Pending
units cannot finance ETF purchases. The event register, issuer distribution row,
panel in-kind value and child close must agree. The cached child feed records a
dividend on 2016-09-07, before entitlement accrual; no child action overlaps the
holding window. Any overlapping child action or missing held-asset quote fails
preflight. All sleeve-risk/total-NAV distinctions in the accounting specification
continue to apply. Synthetic checks and the actual event trace independently
check units, settlement NAV neutrality, sale date and charged costs.

## Fixed selection algorithm

Run all 21 frozen configurations at 5 bp per dollar bought or sold, with the
existing next-open ledger and daily cap monitoring. A is `risk_tolerant_0.02`.
Use annual gross volatility and annual routine buy-plus-sell turnover, excluding
initial entry. Validation estimates are selection inputs, not final evidence.

For B, eligible conventional policies have volatility/daily-MV volatility at
most 1.02. Select minimum turnover, then minimum volatility, then this order:
monthly MV, weekly MV, daily MV, ascending bands, ascending penalties. Neither
equal weight nor another risk-tolerant configuration can be B.

Before observing results, fix absolute numerical equality tolerances to 1e-10
for volatility in decimal annual units and turnover in NAV/year, and 1e-10 for
ratio boundaries. At each tie stage retain candidates within the tolerance of
the exact minimum, then apply the next criterion. This avoids a nontransitive
pairwise floating-point comparator. Eligibility includes the boundary tolerance.

For each secondary family (bands, penalties), match turnover within 10% of A,
then choose minimum volatility, minimum turnover, smaller parameter, using the
same tolerances. If no match exists, minimize absolute turnover distance first,
then volatility, turnover and parameter; explicitly label it unmatched. If A
has zero turnover, only turnover within the absolute tolerance counts as matched.
These settings remain fixed on the final test and across cost sensitivities.

## Evidence and freeze

The entry point offers worker count only, not dates, grid, epsilon, or selection
overrides. Failed runs are retained and cannot supply a selection. Before launch,
save a source snapshot including Python modules/scripts, docs, requirements and
manifests. Require identical source fingerprints after the run. Save bounded
inputs, action mapping, all 21 metrics, ledger/trade/decision/event logs, actual
dependency versions and artifact hashes. Verify every artifact before freezing
B and both secondary comparisons in an exclusive `reports/selections/` folder.
The freeze records the finalized run-manifest hash, selected full configurations,
all selection inputs/eligibility decisions and source/data bindings.

Report all 21 configurations in original order, a risk/turnover plot, A-versus-B
point estimates, and the XLRE event audit. Final-test outcomes are excluded from selection.
