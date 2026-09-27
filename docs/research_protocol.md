**Research protocol — Forecast-Risk Tolerance and Portfolio Rebalancing**

Research design dated 26 September 2026; public text revised 27 September 2026.

The design below was recorded before downloading data or backtesting the financial sample. It was a local protocol, without external preregistration. The dated records at the end describe subsequent data and implementation decisions; editorial revisions do not alter the hypotheses, thresholds or selection rules.

**1. Research question and contribution**

Does accepting a small increase in forecast portfolio volatility allow an equity portfolio to avoid enough trading to improve its realized risk–turnover trade-off relative to credible conventional rebalancing rules?

The economic mechanism is that different portfolio weights can have similar forecast risk. Returning to the exact minimum-variance weights may therefore incur costs with little subsequent risk benefit. Covariance estimation error or slow adaptation could offset this benefit. Calendar or weight-band rules may already capture the available savings.

The study will compare these policies empirically and examine their trading decisions. It does not claim a new optimization theory, an alpha signal, global dynamic optimality, or evidence of institutional execution capacity. Risk, trading costs, and convex portfolio policies are established components of portfolio construction. [Boyd et al., Multi-Period Trading via Convex Optimization](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html)

**2. Primary hypothesis and decision criteria**

The primary proposed policy A uses a fixed 2% relative forecast-volatility tolerance. It will not be replaced by the best-performing tolerance after observing validation or test results.

The primary comparator B is the conventional policy selected by the validation rule in item 7. The two primary test-sample quantities are:

\[
R_\sigma=\frac{\sigma_A}{\sigma_B},\qquad
R_T=\frac{T_A}{T_B},
\]

where sigma is annualized realized gross-return volatility and T is annualized total traded notional divided by contemporaneous pre-trade portfolio value.

The prespecified practical target is at least 20% less turnover with no more than a 2% relative increase in realized volatility: R_T <= 0.80 and R_sigma <= 1.02. These are project-specific screening thresholds chosen before analysis, not industry standards. A 2% relative increase from 15% annualized volatility means 15.3%, an increase of 0.3 percentage points. Forecast tolerance and realized-risk tolerance are separate concepts even though both use 2% here. Results will include absolute annual cost savings in basis points alongside percentage turnover reductions.

Interpretation will distinguish:

- **Strong support:** both thresholds are met by the simultaneous upper confidence bounds described in item 9.
- **Promising but uncertain:** both point estimates meet the thresholds, but the confidence bounds do not establish both.
- **Primary target not established:** the point estimates fail either threshold. This may reflect a different trade-off, little economic benefit, imprecision, or worse performance; the report must identify which.
- **Evidence against the practical claim:** the corresponding simultaneous lower bounds place either ratio above its threshold.

Lower realized volatility at similar turnover can be a useful secondary finding, but it will not be substituted for the primary hypothesis.

**3. Scope and shared assumptions**

| Item | Prespecified choice |
|---|---|
| Instruments | XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY |
| Interpretation | A deliberately selected set of nine tradable sector funds; no claim to reconstruct historical stock constituents or all sectors |
| Portfolio | Long-only equity allocation; fully invested targets; no leverage or tactical cash allocation |
| Position limit | 25% per ETF in each target portfolio |
| Risk inputs | Last 252 complete daily total-return observations available at the decision time |
| Covariance | Ledoit–Wolf shrinkage, estimated on those observations only |
| Forecast objective | Minimum variance; no expected-return forecast |
| Proposed decision frequency | Every eligible trading day |
| Base simulated trading cost | 5 basis points per dollar bought or sold |
| Cost sensitivity | 0, 1, and 10 basis points; same frozen policy settings |
| Trading abstraction | Fractional positions, linear costs, no modeled price impact or capacity claim |
| Annualization | 252 trading days |

The covariance implementation will use the documented estimator and record its configuration. [scikit-learn LedoitWolf documentation](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html)

The ETF universe is chosen before performance analysis. Universe selection and changing underlying exposures remain limitations. Sample coverage, adjustment quality, and tradability assumptions are subject to the data audit.

**4. Formal definition of the proposed policy**

At decision time t, let Sigma_t be the covariance estimate and w_t^- the current allocation after market drift, under the common cash/distribution convention to be finalized before backtesting. Define

\[
\mathcal C=\{w:\mathbf 1^\top w=1,\;0\leq w_i\leq0.25\},
\qquad
v_t^*=\min_{w\in\mathcal C}w^\top\Sigma_t w.
\]

The forecast-risk-tolerance target solves

\[
\min_{w\in\mathcal C}\|w-w_t^-\|_1
\quad\text{subject to}\quad
w^\top\Sigma_t w\leq(1+\epsilon)^2v_t^*.
\]

The primary epsilon is 0.02. The predeclared descriptive grid is {0, 0.01, 0.02, 0.05}; every grid result will be reported. Epsilon zero is also a numerical consistency check against exact minimum variance.

Uniform positive cost rates make minimizing estimated linear cost equivalent to minimizing this weight-turnover objective. Actual executed dollar costs will be calculated separately by the holdings engine. The target calculation is not claimed to minimize exact realized execution costs after an overnight price change and cost funding.

If current holdings satisfy the constraints within certified numerical tolerances, emit KEEP to retain the actual positions, including price drift. If a trade is needed, emit TARGET with the computed weights.

For nonunique trade-minimizing solutions, use a documented lexicographic tie-break: minimize squared distance to current weights among solutions within the certified tolerance of the optimal primary objective. Numerical tolerances will be fixed using synthetic/development checks, never selected from final-test performance.

The risk guarantee concerns the estimated covariance and decision-time target. It does not guarantee realized volatility, executed weights after all frictions, or future optimality. A larger epsilon lowers or preserves optimal cost for a fixed state; it need not lower cumulative turnover along an entire strategy path.

**5. Competing policies**

All minimum-variance-based policies share the covariance estimate and feasible target set.

| Policy | Exact intended behavior |
|---|---|
| Monthly equal weight | Target 1/9 in each fund at the monthly decision; allocation context rather than a candidate for primary comparator B |
| Daily minimum variance | Target a constrained minimum-variance solution every decision day |
| Weekly minimum variance | Form a new minimum-variance target after the last trading close of each calendar week |
| Monthly minimum variance | Form a new minimum-variance target after the last trading close of each calendar month |
| Partial weight-band rule | Recompute the minimum-variance reference daily; choose the minimum-turnover feasible portfolio satisfying abs(w_i - w_i*) <= b for every asset; KEEP if already inside |
| Variance-plus-turnover penalty | Minimize (w' Sigma_t w)/v_t* + lambda * norm1(w - w_t^-) over the common feasible set |

Weight-band widths b are {0.0025, 0.005, 0.01, 0.02, 0.04, 0.08}: 0.25, 0.5, 1, 2, 4, and 8 percentage points of asset weight. They are absolute bands, not percentages of each target weight.

Penalty strengths lambda are {0.01, 0.03, 0.1, 0.3, 1, 3, 10}. Lambda zero is the already-included daily minimum-variance policy. Dividing variance by v_t* makes the penalty parameter dimensionless; this normalization is part of the baseline definition and will be disclosed. It requires v_t* > 0, which must be verified.

The band policy permits partial trades. The penalty policy provides a comparison with the related penalized convex formulation. The study tests a fixed risk tolerance against these preselected alternatives.

Position-cap treatment is common: inspect caps daily. A calendar or KEEP policy whose current allocation breaches a cap receives a minimum-turnover target repair into C, with the same lexicographic tie-break. A policy already producing a feasible target uses that target. Execute repairs with the same lag and costs as other trades. Label calendar policies as “weekly/monthly plus daily cap monitoring,” report repair trades separately, and do not claim continuous intraday cap compliance.

**6. Timing, accounting, and data requirements**

The intended execution convention is: estimate and choose a target after close t using information available through that close; execute at the next session's opening prices. Freeze the signal and target before that opening. Mechanical sizing uses execution prices, while the signal and target remain fixed. KEEP means no discretionary trade. New holdings receive only returns after their actual simulated execution.

Target execution must pay costs from existing portfolio wealth. Record target weights, pre-trade holdings, actual trades, cash, post-trade holdings, and any target-versus-execution discrepancy. The weight-level optimizer and funded execution ledger must not silently use incompatible cost definitions. The self-financing requirement is standard portfolio accounting. [MOSEK Portfolio Optimization Cookbook, transaction costs](https://docs.mosek.com/portfolio-cookbook/transaction.html)

Use a consistent treatment of splits, distributions, and reinvestment; do not double count dividends or treat an adjusted price as an executable cash price. Exact dividend settlement/reinvestment, residual cash, and order-sizing mechanics are dependencies of the accounting specification, not facts already established by this protocol. These must be settled and frozen before performance analysis. The chosen convention must preserve comparability across strategies and disclose any total-return/reinvestment approximation.

No unrestricted filling of missing prices, silent removal of difficult dates, or hidden substitution of tickers is allowed. Data problems must be investigated and logged. If next-open execution cannot be supported credibly by available data, amend the protocol before running performance comparisons; do not silently change the timing model.

Run each cost scenario through the funding/holdings engine. Uniformly scaling the target objective's cost coefficient does not change its solution at a fixed state, although funding differences can affect subsequent portfolio paths.

**7. Development, validation, and comparator selection**

Subject to common usable history, use:

| Period | Permitted use |
|---|---|
| Observations before 2005 | At least 504 complete returns to support the longest prespecified window; the base model uses 252 |
| 2005–2014 | Development, debugging, synthetic and accounting validation |
| 2015–2019 | The prespecified comparator and turnover-matching selection rules |
| 2020–2025 | Final held-out policy evaluation |

Every block begins from a common equal-weight allocation and common initial capital, with the same entry-cost convention. Earlier returns may initialize covariance estimates; strategy holdings are reset at block boundaries. Report initial investment costs separately from subsequent rebalancing turnover. There is no forced liquidation at the end. Exact first signal/fill timestamps will be specified in the accounting document.

Select comparator B on 2015–2019 at the base cost using this deterministic rule:

1. Evaluate every conventional candidate in item 5, excluding equal weight.
2. Retain candidates with realized gross-return volatility at most 1.02 times that of daily minimum variance on validation.
3. Select the retained candidate with the lowest annualized rebalancing turnover.
4. Break ties by lower volatility, then the fixed ordering: monthly, weekly, daily, band widths ascending, penalty strengths ascending. Numerical equality uses a documented fixed tolerance.

Daily minimum variance guarantees a feasible selection candidate. The validation ceiling is a selection device, not a promise of test-sample risk compliance. No final-test outcome enters selection, and B remains fixed across the cost sensitivities.

For the secondary matched-turnover comparison, select one band setting and one penalty setting whose validation turnover is within 10% of policy A's. Among qualifying settings select the lowest validation volatility, then lower turnover, then the smaller parameter. If none qualify, choose the closest turnover and label the comparison unmatched. Never retune to match realized test-sample turnover or interpolate a hypothetical tradable policy between test results. Report all calendar points and all grid points as descriptive context.

Structural changes to strategies or parameter grids may be made during development only through a dated amendment. Once validation results have influenced such changes, that period is no longer an untouched validation set. After the selection run, save code, configurations, data hashes, and the selected comparator before computing final-test results.

**8. Metrics and required exhibits**

Let D_t be total actual dollar purchases plus sales at an execution, and V_t^- pre-trade wealth. Define q_t = D_t / V_t^-; use zero on dates without executions. If there are multiple executions in a session, sum their separately normalized traded notionals. With N the number of trading days in the evaluated block, define

\[
T=\frac{252}{N}\sum_{t=1}^{N}q_t.
\]

This is total traded notional; it is not the half-turnover convention. A sale of 10% of NAV and purchase of 10% of NAV contributes approximately 20% total traded notional. Linear cost at uniform rate c is c * D_t; a cost rate quoted per dollar traded applies to both sides. Routine rebalancing turnover excludes the common initial purchase but includes policy trades, cap repairs, and any charged reinvestment trades, each identified separately.

Primary realized volatility is sqrt(252) times sample standard deviation of daily gross portfolio returns, removing explicit trading-cost debits while retaining the executed exposure path. The accounting specification must define the interval return attribution exactly. Also report net-return volatility and the full net wealth path so costs are not omitted from the economic results.

Additional metrics: annual cost debit rate, no-discretionary-trade fraction, net compound return, maximum drawdown, maximum weight and concentration, cap repairs, solver failures, cash exposure, and forecast-risk ratios relative to v_t*. Record risk ratios at decision and after execution using appropriately dated information. Distinguish compliant targets from any later drift or execution differences.

Required exhibits:

- Realized volatility versus turnover for all prespecified policies; highlight A, B, and the validation-selected matched comparisons without selecting a winning test parameter.
- A table of A versus B with risk and turnover ratios, uncertainty intervals, cost savings, and net outcomes at each cost assumption.
- Forecast-risk compliance and concentration diagnostics.
- Trading-decision examples selected by a reproducible rule: the first qualifying KEEP event and first qualifying partial-rebalance event in the test sample, plus the largest trade. If an event does not occur, report its absence. Any additional hand-selected episode must be labeled illustrative.

**9. Uncertainty and historical stability**

For the primary A/B comparison, jointly resample the aligned daily gross returns and turnover records using a paired stationary block bootstrap: 5,000 replications, expected block length 20 trading days, seed 20260926. Use expected lengths 10 and 60 as predeclared sensitivity checks. Do not resample each strategy independently. [arch time-series bootstrap documentation](https://bashtage.github.io/arch/bootstrap/timeseries-bootstraps.html)

Report ordinary 95% percentile intervals for each ratio. For the strong-support decision, use a 97.5% one-sided upper bound for each ratio, giving nominal 95% simultaneous upper coverage via a Bonferroni adjustment. For evidence against the target use the analogous simultaneous lower bounds. These are approximate bootstrap statements under time-series assumptions, not exact finite-sample guarantees. If a denominator or bootstrap statistic is undefined, report the issue and do not claim significance.

This resamples the recorded outcomes of frozen policies. It does not regenerate covariance estimates and trading paths inside each bootstrap sample, correct data mining, or prove transportability to other market regimes. Serial dependence and structural change can limit inference.

Show each test calendar year, the three fixed blocks 2020–2021, 2022–2023, and 2024–2025, and leave-one-year-out effect sizes. Those checks are descriptive, not six extra confirmatory hypothesis tests. Secondary grid comparisons will not be advertised as independently significant discoveries.

**10. Limited robustness and mechanism checks**

Predeclare these separate, one-at-a-time experiments:

- Risk-estimation windows of 126 and 504 returns, retaining the same estimator.
- Sample covariance in place of Ledoit–Wolf.
- Diagonalized Ledoit–Wolf covariance, applied consistently to all covariance-dependent policies, to investigate the importance of off-diagonal correlation information.
- Execution one additional session later: after close t, fill at open t+2, with frozen instructions.
- Trading-cost scenarios specified in item 3.

The diagonal experiment changes both targets and triggers, so it cannot alone identify a pure causal contribution of covariance-aware tolerance geometry. Interpret it together with the partial-band comparison and individual decisions.

Keep selected parameters fixed and avoid a Cartesian product of every setting. Recompute each policy's rolling risk model when its estimator/window changes, but do not reselect B or tune parameters on the test sample. Report all prespecified checks, including inconvenient results. Later checks suggested by test outcomes are exploratory and must be labeled that way.

**11. Verification and interpretation**

Before final evaluation, verify future-data perturbation invariance of earlier decisions; hand-calculated holdings/cash examples; correct post-fill return timing; funded transaction costs; feasible targets; KEEP behavior; epsilon-zero consistency; fixed-state tolerance monotonicity; and explicit solver failure handling. The test suite must check economic/accounting invariants as well as solver output.

Solver exceptions must be recorded as failures, not KEEP instructions. The implementation must specify retry, certification, and failure reporting before final evaluation; unresolved invalid decisions block claims based on affected runs.

The report will present the specified comparisons and limitations, including results that favor a conventional baseline.

The study cannot establish persistent alpha, high-frequency execution skill, live profitability, capacity, global dynamic optimality, or suitability of the allocation for an investor. The historical holdout restricts policy tuning; the market events themselves were already known.

**12. Dependencies, freeze, and amendment record**

Before strategy-performance analysis, settle and record:

- Data vendor, access terms, raw fields, adjustment/distribution conventions, common sample coverage, independent cross-checks, and data snapshot hashes.
- Dividend/cash/reinvestment treatment, target-to-order sizing, funded execution, return attribution, initialization timestamps, and cap repair mechanics.
- Deterministic numerical tolerances, solution tie-break implementation, and solver failure behavior.

If coverage prevents the proposed dates, choose an amended chronological split using coverage information only, before examining comparative performance. Do not shorten the sample because of poor strategy results.

Data-quality checks may inspect the whole dataset; candidate-policy performance on 2020–2025 remains unopened until the selection freeze. The holdout therefore applies to policy outcomes, not all observations from that period.

Each amendment records the date, what changed, why, which periods' data and results had already been inspected, and whether the analysis remains confirmatory or becomes exploratory. A bug discovered after opening the test set may be corrected and all affected runs repeated, but both the defect and the rerun must be disclosed. Repeated design changes cannot restore an already-used holdout.

Version 1.0 record: protocol created; no financial data downloaded or strategy performance inspected in this project. 

**Data-audit amendment — 26 September 2026**

The original version-1.0 record above describes its creation state. Since then, daily instrument prices, distributions and data-quality diagnostics have been inspected across the whole available history, including 2020–2025; no candidate-policy performance, covariance estimates or portfolio results have been calculated. The universe, chronological split, hypotheses, thresholds, comparator-selection rules and robustness experiments are unchanged.

Sources are a frozen Yahoo chart snapshot, issuer fund/distribution/NAV/premium files and event-specific evidence. The available common price panel is 1998-12-22 through 2025-12-31; 2003–2004 supplies 504 complete warmup returns per asset. Raw 2026 observations support adjustment reconstruction only and are excluded from the study panel. These are retrospective snapshots, not point-in-time vendor publication archives.

The data audit separates provider-adjusted prices, reconstructed nominal prices, genuine share splits, cash distributions and XLF's XLRE share entitlement. One XLP cash entry is adjudicated from a contemporaneous exchange announcement; ten cash observations remain unresolved and are quarantined. At this point, cash accounting and in-kind disposal were still under development, and unresolved events blocked financial analysis. The later evidence amendment below records the corrected source assessment; current sample status is in [data availability](data_availability.md).

This amendment records source and quality decisions made before strategy results. It does not reclassify any performance-driven analysis as confirmatory.

**Numerical implementation record — 26 September 2026**

The risk estimator, minimum-variance reference, risk-tolerance targets, weight-band targets, variance-penalty targets and cap repair are implemented. Numerical scaling, tolerances, distance tie-breaks, independent objective bounds and deterministic retries are implemented in [optimization.py](../src/risk_rebalancing/optimization.py). Numerical choices were developed on analytic and seeded synthetic examples; no financial strategy performance, covariance estimate or portfolio target was computed on the ETF history. Previously permitted market-data QA and its unresolved issues are unchanged.

The primary L1 optimality-gap threshold is 2e-7, the distance tie-break adds at most 1e-7 to the achieved primary turnover budget before the 1e-8 feasibility tolerance, and the squared-distance objective also has an independent 2e-7 gap threshold. An inaccurate solver status may qualify only in that secondary solve and only after all independent checks pass; the original status is retained. A numerical restoration toward the primary feasible target is logged and must pass the same final checks. Invalid decisions raise an error and never silently become KEEP.

These numerical checks preceded the holdings engine and its calendar, cash-settlement and execution rules. Financial data review was still incomplete.

**Accounting implementation record — 26 September 2026**

The accounting conventions are now frozen in `accounting_specification.md`: nominal fractional shares; ex-date cash/child receivables; after-pay-date-close settlement; next-open proportional cash reinvestment or delivered-child sale; frozen close-to-next-open targets funded exactly from existing wealth; distinct initial-entry, policy, cap-repair, reinvestment and auxiliary-sale costs; and gross returns obtained by removing each actual cost debit at its charged instant. The two-session delay retains outstanding instructions in FIFO order. Block entry is equal weight at the first open, with first policy decision after that close; blocks inherit no earlier distribution rights and impose no terminal liquidation.

The optimizer's fully invested current weights and 25% caps refer explicitly to the ETF sleeve, calculated from actual drifted ETF holdings. Settled cash and cash/child receivables remain in total NAV and exposure diagnostics. Cash is mechanically deployed when available. Transient distributed-child exposure is outside the ETF covariance model, so the forecast-risk constraint is a sleeve guarantee, not a bound on total-NAV risk during that exposure. Realized gross/net returns include the entire marked portfolio. This resolves the cash mapping previously reserved in items 4, 6 and 12.

Synthetic verification now covers the connected risk/policy/ledger pipeline, hand-calculated event and funding cases, future-data perturbations, holiday-aware calendar boundaries, explicit failures and unchanged financial snapshots. No financial covariance estimate, portfolio target or candidate-policy performance was computed. Data QA previously inspected the whole history; ten cash amount disagreements and the recorded payment-date reconciliation still block financial release. Universe, research hypothesis, parameter grids, sample split, comparator-selection rules and inference plan are unchanged.

**Evidence and development-runner amendment — 26 September 2026**

The cached file previously described as the NYSE dividend announcement was discovered to contain a website challenge page. Its bytes are preserved but its evidence classification is rejected. File-length validation has been replaced with challenge detection plus source-hash/provenance and exact distribution-row checks for each correction. The XLP 2009-12-18 amount of USD 0.24865 is independently supported by the fund distributor's archived 2009 table (captured in 2013), which gives payment on 2009-12-30. That date agrees with the current issuer schedule and resolves the previous disagreement with the republished announcement's 12/31 date.

The fund distributor's archived API (captured in 2023) gives XLF's 2016-03-18 payment as USD 0.123, payable 2016-03-29. This corroborates the current issuer amount USD 0.122995 within USD 0.000005; retain that amount rather than the reconstructed Yahoo value. These archived histories are primary distributor records, but are not contemporaneous point-in-time publication snapshots of those events. All nine archived September 2006 tables show only two-decimal amounts; no precise override or rounding rule is inferred. Nine cash amounts remain unresolved, and financial release remains false.

The fixed development runner, 21-policy configuration grid, evidence-aware release guard, nominal-price/cash-event adapter, metrics and append-only experiment records are implemented. Tests use artificial data; no financial covariance, target or strategy return has been computed. There is no change to the universe, time split, parameters, hypothesis, validation selection or inference plan. At this date, unresolved 2006 evidence blocked the strict development release and validation/final outcomes had not been computed. Subsequent development used labelled provisional scenarios; [validation](validation_specification.md) and [final evaluation](final_evaluation_specification.md) use separately reviewed windows that exclude those events.
