# Holdings, execution and return accounting

Specification dated 26 September 2026, fixed during synthetic development before financial strategy evaluation. The rules below define holdings, event timing, trade funding and portfolio returns.

## 1. State, price units and model boundary

The state consists of fractional nominal shares, settled USD cash, fixed-dollar cash receivables, and pending or delivered auxiliary shares. NAV is their marked total. Cash receivables are valued at face value; no interest, withholding tax, default discount or receivable financing is modeled. Auxiliary shares require contemporaneous positive prices whenever exposed, including before delivery. Missing prices on unheld auxiliary assets are permitted; missing required prices fail the run. ETF open/close prices must be positive and complete on the supplied exchange calendar. Missing risk-return sessions cannot be silently skipped.

Execution uses contemporaneous **nominal, unadjusted share prices**. Execution prices are reconstructed in nominal share units; backward-adjusted provider prices cannot be used directly for cash accounting. The instrument total-return series is a separate covariance input. Dividends must not be added to dividend-adjusted execution returns.

The ledger supports fractional positions, uniform proportional costs, immediately nettable trade proceeds and deterministic recorded corporate actions. It does not model brokerage trade settlement, integer lots, spread dynamics, volume limits, taxes, price impact, securities lending or order-book fills. Dividend pay-date handling does not imply that stock-sale settlement has been modeled. A target sized to opening prices is an execution abstraction; the strategy may not refit its signal at that opening.

## 2. Mapping actual holdings into the optimizer

For the nine ETFs, let `a_i = shares_i × close_i`. The optimizer's current allocation is `w_i = a_i / sum(a)`, the weights **within the ETF holdings**. Its target sums to one, and the 25% cap applies to these sleeve weights. Cash and receivables are excluded from this normalization but remain in NAV, reported exposures and realized returns. Reinvestment is mechanical and common to every policy; cash is not an allocation decision.

This explicitly limits the forecast-risk guarantee to the ETF sleeve. A distributed XLRE entitlement has price risk outside that modeled sleeve until it is sold. No bound on total-NAV forecast variance is claimed during such exposure. Record settled cash, cash/child receivables, auxiliary exposure, sleeve concentration and ETF weights relative to full NAV. Receivable and auxiliary fractions overlap for pending child shares and must not be summed as disjoint exposures; their underlying component values are reported separately.

Targets are certified by the portfolio optimizer. The engine rejects malformed or cap-infeasible targets. Optimizer and engine cap settings must agree. Cap breaches caused by intervening price changes are observable drift, not a claim of continuous cap compliance.

## 3. Session event order

At every simulated session, perform the following sequence:

1. Before the open, apply genuine splits to held positions and pending child-share units. Accrue that session's distribution entitlements from the positions held **before** opening trades. Cash amounts are specified per share in the units after any same-day split.
2. Mark opening NAV, including cash and receivables. Sell any child shares delivered after a prior close, charging costs; proceeds are available for the opening ETF order.
3. At the block's first open, buy equal weights. Otherwise, execute the dated frozen TARGET due at that open. If there is no TARGET, deploy available cash proportionally to the **current opening ETF weights**. A due KEEP never restores yesterday's weights.
4. Mark closing NAV. Convert payable cash/child receivables after the pay-date close without changing NAV. A non-session pay date is processed after the first session's close on or after that date. Cash/child shares are usable at the following open. This deliberately conservative availability convention is a model assumption, not a statement about a particular broker's intraday crediting practice.
5. Pass the policy actual closing sleeve weights and only risk-return observations dated through that close. Compute the dated risk model and issue KEEP or a frozen TARGET for open `t+1`; the prespecified delay sensitivity uses open `t+2`.

An ex-date buyer receives no entitlement to that distribution. Selling after accrual does not extinguish the receivable. Cash receipt is not a new investment return or external contribution: the value was recognized at accrual. A genuine 2:1 split doubles share count while halving the price unit, without generating trading or income. XLF's 2016 distribution instead creates XLRE units and leaves the XLF share count unchanged.

Pending child units are marked to the child's prices; they cannot be sold before delivery or used to fund ETF purchases. Splits of the child adjust pending units. A further distribution on an undelivered child requires explicit beneficial-rights adjudication and currently raises an error. This prevents the generic engine from inventing a due-bill convention. Such an overlap is not assumed in the reviewed XLF/XLRE event.

The initial implementation accepts in-kind children outside the chosen ETF universe. It rejects an in-universe child rather than confusing mandatory disposal with existing policy holdings. Individual event records require unique IDs and unique economic keys; cash components must be explicitly aggregated before loading.

## 4. Funded position sizing and costs

At an execution, let `a` be the ETF dollar holdings, `C` settled cash, `B = sum(a) + C` the investable budget, `w` the frozen target, and `c` the cost per dollar purchased or sold. Pending receivables are not included in B. Solve for post-cost ETF wealth S:

\[
S + c\sum_i |w_i S-a_i| = B.
\]

Then set nominal shares to `w_i S / open_i`. For `0 <= c < 1`, the left side is strictly increasing in S, with a root on `[0,B]`; use 90 bisection iterations and retain the funded lower endpoint. The derivative, where defined, is at least `1-c`. At zero cost use `S=B`. Residual floating-point cash remains in the portfolio.

This scalar equation applies the standard self-financing cost budget to a frozen target; costs are funded from existing wealth. [MOSEK Portfolio Optimization Cookbook, transaction costs](https://docs.mosek.com/portfolio-cookbook/transaction.html)

Traded notional is the sum of absolute **dollar purchases plus dollar sales**, with cost `c × notional`. Initial all-cash entry gives `S=B/(1+c)`. A sale and purchase both incur costs. Every cost scenario must run its own ledger, because funding can change later holdings and decisions.

At a scheduled TARGET, all available cash and ETF holdings are sized together in one net ETF trade. There is no duplicate preliminary reinvestment. Without a TARGET, reinvestment uses the drifted opening sleeve weights, preserving the sleeve allocation apart from roundoff. Delivered auxiliary shares are sold separately before this step, so child liquidation and ETF purchases both incur their respective costs.

The decision-time L1 optimizer minimizes weight distance at the prior close. The realized dollar cost depends on intervening prices and funding; this engine does not claim that the prior-close target minimizes exact opening execution cost.

## 5. Instructions, calendar rules and block boundaries

Monthly and weekly decisions occur after the last trading close in the relevant calendar month or Monday–Sunday week. Determine the boundary from the **next actual exchange session**, not the next quoted row after a truncated run. A future calendar buffer must support all queued execution dates. Holiday-shortened weeks are therefore handled without assuming Friday is open.

The policy adapter fits the common dated covariance/reference each session, including calendar KEEP days, providing comparable diagnostics and making missing risk inputs fail explicitly. It implements monthly equal weight; daily, weekly and monthly minimum variance; daily tolerance, partial-band and variance-penalty decisions. On an off-schedule day, a calendar policy with a cap breach emits a minimum-turnover cap repair, labeled separately. Solver errors propagate and stop the run.

With the two-session delay, each instruction remains in a date-indexed FIFO queue. A newer KEEP does not cancel an older TARGET. Signals use current actual holdings, not projected holdings after pending fills. One daily instruction implies at most one discretionary ETF target at any opening. Every terminal queued instruction is retained as unfilled, including terminal KEEP observations; no target is filled beyond the run boundary.

Each development, validation or evaluation block starts anew with the same capital in cash, buying equal weights at its first open. It inherits no earlier holdings or distribution entitlements. The first strategy decision occurs after that first close, using available historical warmup returns. Initial purchase costs are included in NAV/net returns and recorded separately from routine turnover. There is no forced final liquidation. Terminal settled cash, delivered auxiliary positions and outstanding receivables remain in NAV. Corporate actions whose ex-date preceded block entry do not grant new entitlements.

## 6. Gross/net returns and turnover

Let `V_prev` be previous closing NAV (initial cash on the first day), `V_close` current closing NAV, and `V_j^-`, `V_j^+` the NAV immediately before and after each same-day cost-bearing execution j, marked at the same prices. There are no external flows. Define

\[
r_t^{net}=V_{close}/V_{prev}-1,\qquad
1+r_t^{gross}=\frac{V_{close}}{V_{prev}}\prod_j\frac{V_j^-}{V_j^+}.
\]

The gross series removes explicit cost debits at the instant charged while retaining the actual funded exposure path. It is a time-weighted attribution, not a separate zero-cost strategy. All charged events, including entry, child sale and reinvestment, enter the removal factor. Adding the day's cash fees to the terminal NAV is generally incorrect when later price movements occur. At zero costs, gross and net coincide.

For each event, routine turnover is `D_j / V_j^-`, except that initial entry contributes zero routine turnover. Sum separately normalized events within each session. Annual turnover is `252/N` times the sum over the block. Reinvestment, auxiliary disposal and cap repairs count; none receive free trading. Log actual USD costs and cost/NAV debit fractions by reason, keeping initial entry separate. There is no forced terminal liquidation.

`discretionary_trade` identifies an executed policy or cap-repair trade above the numerical dust threshold. A KEEP day may still contain a split, settlement, child sale or cash reinvestment. Signal KEEP frequency and realized no-discretionary-trade frequency are reported separately.

## 7. Numerical rules, output and reproducibility

- Costs must be finite and in `[0,1)`; the study scenarios are 0, 1, 5 and 10 bps. Initial capital and marked prices must be finite and positive.
- Target sum error may not exceed `1e-10`; normalization only removes machine rounding. Target cap tolerance is `1e-8`, matching the certified model convention. No materially negative position or cash balance is permitted.
- Funded sizing residual tolerance is `max(1e-10 USD, 1e-12 × investable budget)`. A negative residual cash value within this tolerance can be floored to zero; the resulting funding discrepancy is logged. Larger deficits raise.
- After each trade, require `NAV_before - NAV_after = cost` within `max(1e-9 USD, 2e-12 × NAV_before)`. Settlement must preserve NAV at the same tolerance. Reinvestment and discretionary-trade reporting ignore only cash/notional dust below `max(1e-10 USD, 1e-12 × NAV)`; any retained cash is still in NAV.
- Core logs retain signal/due dates, policy diagnostics, opening prices, pre/post shares and cash, signed dollar trades, notional, costs, sizing residuals, target discrepancies, and filled-sleeve risk under the **signal's dated covariance**. The engine does not refit at the open. No forced failure recovery, silent date deletion or price filling is allowed.

The ledger and policy implementations are in [ledger.py](../src/risk_rebalancing/ledger.py) and [policies.py](../src/risk_rebalancing/policies.py). Run `python scripts/reproduce.py check` for the regression suite or `python scripts/reproduce.py demo` for a synthetic example. Financial replay validates the five reviewed input files before constructing the market tape.

## 8. Data scope

The accounting specification defines event handling and funding conventions. Data review must separately establish each event's amount, units, ex-date and payment date. Nine September 2006 cash amounts remain unresolved in provisional development; they are outside the reviewed validation and final-evaluation windows. See [data availability](data_availability.md).
