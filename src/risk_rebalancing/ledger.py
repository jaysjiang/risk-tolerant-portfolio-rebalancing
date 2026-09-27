"""Nominal-price, fractional-share ledger with explicitly timed distributions.

This module accepts a validated market tape. It does not download or release data.
Study entry points must pass the project's data-release guard before constructing
a financial tape. Synthetic tapes exercise the accounting tests.
"""
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


def session(value):
    date = pd.Timestamp(value)
    if pd.isna(date) or date.tzinfo is not None or date != date.normalize():
        raise ValueError("Sessions must be finite, timezone-naive calendar dates")
    return date


def date_index(values, name):
    index = pd.DatetimeIndex([session(x) for x in values])
    if index.empty or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError(f"{name} must be nonempty, unique and increasing")
    return index


@dataclass(frozen=True)
class CorporateAction:
    event_id: str
    kind: str  # split, cash, in_kind
    ticker: str
    ex_date: pd.Timestamp
    amount: float  # new/old ratio, USD/share, or child shares/parent share
    pay_date: pd.Timestamp | None = None
    child: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "ex_date", session(self.ex_date))
        if self.pay_date is not None:
            object.__setattr__(self, "pay_date", session(self.pay_date))
        if not self.event_id or self.kind not in {"split", "cash", "in_kind"}:
            raise ValueError("Invalid corporate action identity or kind")
        if not np.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("Corporate action amount must be positive")
        if self.kind == "split":
            if self.pay_date is not None or self.child is not None:
                raise ValueError("Split is effective before ex-date open, without pay date")
        elif self.pay_date is None or self.pay_date < self.ex_date:
            raise ValueError("Distribution pay date must be on or after ex date")
        if (self.kind == "in_kind") != (self.child is not None):
            raise ValueError("Only in-kind actions must specify a child")
        if self.child == self.ticker:
            raise ValueError("In-kind child must differ from parent")


@dataclass(frozen=True)
class MarketTape:
    tickers: tuple[str, ...]
    opens: pd.DataFrame
    closes: pd.DataFrame
    risk_returns: pd.DataFrame
    calendar: pd.DatetimeIndex
    actions: tuple[CorporateAction, ...] = ()
    price_basis: str = "nominal_unadjusted"

    def __post_init__(self):
        if self.price_basis != "nominal_unadjusted":
            raise ValueError("Execution requires nominal_unadjusted prices")
        names = tuple(self.tickers)
        if not names or len(set(names)) != len(names) or not all(isinstance(x, str) and x for x in names):
            raise ValueError("ETF labels must be unique nonempty strings")
        object.__setattr__(self, "tickers", names)
        cal = date_index(self.calendar, "Trading calendar")
        object.__setattr__(self, "calendar", cal)
        frames = []
        for name, original in (("opens", self.opens), ("closes", self.closes)):
            frame = original.copy(deep=True)
            frame.index = date_index(frame.index, name)
            if frame.columns.has_duplicates or not set(names).issubset(frame.columns):
                raise ValueError("Quote columns must be unique and contain the ETF universe")
            if not all(isinstance(x, str) and x for x in frame.columns):
                raise ValueError("Quote columns must be nonempty strings")
            frame = frame.astype(float)
            if not frame.index.isin(cal).all():
                raise ValueError("Quote dates must be trading sessions")
            values = frame.to_numpy()
            if np.isinf(values).any() or ((values <= 0) & ~np.isnan(values)).any():
                raise ValueError("Nonmissing prices must be finite and positive")
            if frame.loc[:, list(names)].isna().any().any():
                raise ValueError("ETF prices cannot be missing")
            frames.append(frame)
            object.__setattr__(self, name, frame)
        if not frames[0].index.equals(frames[1].index) or not frames[0].columns.equals(frames[1].columns):
            raise ValueError("Open and close grids must match")
        # A partial quote sample may not hide an intervening trading session.
        expected = cal[(cal >= frames[0].index[0]) & (cal <= frames[0].index[-1])]
        if not expected.equals(frames[0].index):
            raise ValueError("Missing trading session in quote tape")
        returns = self.risk_returns.copy(deep=True)
        returns.index = date_index(returns.index, "Risk returns")
        if returns.columns.has_duplicates or set(returns.columns) != set(names):
            raise ValueError("Risk-return columns must match ETF universe")
        if not returns.index.isin(cal).all():
            raise ValueError("Risk-return dates must be trading sessions")
        expected_returns = cal[(cal >= returns.index[0]) & (cal <= returns.index[-1])]
        if not expected_returns.equals(returns.index) or not frames[0].index.isin(returns.index).all():
            raise ValueError("Risk returns must cover quote dates without skipped trading sessions")
        object.__setattr__(self, "risk_returns", returns.loc[:, list(names)].astype(float))
        actions = tuple(self.actions)
        if len({a.event_id for a in actions}) != len(actions):
            raise ValueError("Duplicate action identifier")
        keys = [(a.kind, a.ticker, a.ex_date, a.child) for a in actions]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate economic action; aggregate components explicitly")
        for action in actions:
            if action.ex_date not in cal:
                raise ValueError("Ex date must be a trading session")
            if action.ticker not in frames[0].columns:
                raise ValueError("Corporate action ticker lacks a quote column")
            if action.kind == "in_kind" and (action.child not in frames[0].columns or action.child in names):
                raise ValueError("In-kind child must be an auxiliary quoted asset outside the ETF sleeve")
        object.__setattr__(self, "actions", actions)


@dataclass(frozen=True)
class Instruction:
    action: str
    target_weights: tuple[float, ...] | None = None
    reason: str = "policy"
    policy: str = "scripted"
    diagnostics: dict = field(default_factory=dict)
    covariance: tuple[tuple[float, ...], ...] | None = None
    reference_variance: float | None = None

    def __post_init__(self):
        if self.target_weights is not None:
            object.__setattr__(self,"target_weights",tuple(self.target_weights))
        if self.covariance is not None:
            object.__setattr__(self,"covariance",tuple(tuple(row) for row in self.covariance))


@dataclass(frozen=True)
class CloseContext:
    date: pd.Timestamp
    next_session: pd.Timestamp
    tickers: tuple[str, ...]
    current_weights: tuple[float, ...]
    nav: float
    settled_cash: float
    receivable_value: float
    auxiliary_value: float  # settled + pending child market value
    risk_returns: pd.DataFrame  # isolated copy, no future observations


@dataclass(frozen=True)
class FundedTarget:
    post_values: tuple[float, ...]
    cash: float
    cost: float
    traded_notional: float
    post_etf_wealth: float
    funding_residual: float


def fund_target(current_values, settled_cash, target_weights, cost_rate):
    """Solve S + c*||w*S-a||_1 = sum(a)+cash, without external funding."""
    a = np.asarray(current_values, dtype=float)
    w = np.asarray(target_weights, dtype=float)
    c = float(cost_rate)
    if a.ndim != 1 or w.shape != a.shape or a.size == 0:
        raise ValueError("Holdings and target must be matching nonempty vectors")
    if not np.isfinite(a).all() or (a < 0).any() or not np.isfinite(settled_cash) or settled_cash < 0:
        raise ValueError("Holdings and settled cash must be nonnegative and finite")
    if not np.isfinite(w).all() or (w < 0).any() or abs(w.sum()-1) > 1e-10:
        raise ValueError("Target must be finite, nonnegative and sum to one")
    if not np.isfinite(c) or not 0 <= c < 1:
        raise ValueError("Cost rate must be in [0,1)")
    w = w / w.sum()  # machine-rounding normalization only, bounded above
    budget = float(a.sum() + settled_cash)
    if budget <= 0:
        raise ValueError("Investable budget must be positive")
    if c == 0:
        wealth = budget
    else:
        lo, hi = 0., budget
        for _ in range(90):
            mid = (lo+hi)/2
            if mid + c*float(np.abs(w*mid-a).sum()) <= budget:
                lo = mid
            else:
                hi = mid
        wealth = lo
    values = w * wealth
    notional = float(np.abs(values-a).sum())
    cost = c * notional
    residual_cash = budget-float(values.sum())-cost
    tolerance = max(1e-10, budget*1e-12)
    if residual_cash < -tolerance:
        raise ArithmeticError("Target sizing created unfunded purchases")
    # Only a floating-point residual may be floored; the discrepancy is logged.
    cash = max(0., residual_cash)
    residual = budget-float(values.sum())-cash-cost
    return FundedTarget(tuple(values), cash, cost, notional, float(values.sum()), residual)


@dataclass
class Receivable:
    event_id: str
    pay_date: pd.Timestamp
    kind: str
    amount: float
    asset: str | None = None


@dataclass(frozen=True)
class SimulationResult:
    daily: pd.DataFrame
    trades: tuple[dict, ...]
    signals: tuple[dict, ...]
    events: tuple[dict, ...]
    outstanding_receivables: tuple[dict, ...]
    final_shares: dict[str, float]
    final_cash: float


class HoldingsEngine:
    def __init__(self, tape: MarketTape, *, cost_rate=0.0005, cap=0.25, execution_lag=1):
        if not np.isfinite(cost_rate) or not 0 <= cost_rate < 1:
            raise ValueError("Cost rate must be in [0,1)")
        if not np.isfinite(cap) or not 0 < cap <= 1 or cap*len(tape.tickers) < 1-1e-12:
            raise ValueError("Infeasible sleeve cap")
        if execution_lag not in (1, 2):
            raise ValueError("Execution lag must be one or two sessions")
        self.tape, self.cost_rate, self.cap, self.lag = tape, float(cost_rate), float(cap), execution_lag

    def run(self, policy: Callable[[CloseContext], Instruction], *, start=None, end=None, initial_capital=1_000_000.):
        """Start a fresh block in cash; buy equal weight at its first open."""
        tape = self.tape
        if hasattr(policy,"cap") and abs(policy.cap-self.cap)>1e-12:
            raise ValueError("Policy and engine sleeve caps must agree")
        start = session(start if start is not None else tape.opens.index[0])
        end = session(end if end is not None else tape.opens.index[-1])
        if start not in tape.opens.index or end not in tape.opens.index or start > end:
            raise ValueError("Run boundaries must be quoted sessions in order")
        if not np.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError("Initial capital must be positive and finite")
        if tape.calendar.get_loc(end)+self.lag >= len(tape.calendar):
            raise ValueError("Trading calendar requires future buffer for scheduling and lag")
        dates = tape.opens.loc[start:end].index
        assets, names = tuple(tape.opens.columns), tape.tickers
        shares = {name: 0. for name in assets}
        cash = float(initial_capital)
        receivables, trades, signals, events, daily, queue = [], [], [], [], [], {}
        previous_nav = cash

        def quote(prices, asset):
            value = float(prices[asset])
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"Missing required quote for held/receivable asset {asset} on {prices.name}")
            return value

        def components(prices):
            etf = sum(shares[n]*quote(prices,n) for n in names)
            settled_aux = sum(q*quote(prices,n) for n,q in shares.items() if n not in names and q != 0)
            cash_receivable = sum(r.amount for r in receivables if r.kind == "cash")
            child_receivable = sum(r.amount*quote(prices,r.asset) for r in receivables if r.kind == "in_kind")
            return {"etf_value": etf, "settled_cash": cash, "cash_receivable": cash_receivable,
                    "child_receivable": child_receivable, "settled_auxiliary": settled_aux,
                    "nav": etf+cash+cash_receivable+child_receivable+settled_aux}

        def sleeve_weights(prices):
            values = np.array([shares[n]*quote(prices,n) for n in names])
            if values.sum() <= 0:
                raise ArithmeticError("ETF sleeve has no investable value")
            return values/values.sum()

        def validate_instruction(instruction):
            if not isinstance(instruction, Instruction) or instruction.action not in {"KEEP", "TARGET"}:
                raise ValueError("Policy must emit a valid Instruction")
            if instruction.action == "KEEP":
                if instruction.target_weights is not None:
                    raise ValueError("KEEP must not contain a target")
            else:
                w = np.asarray(instruction.target_weights, dtype=float)
                if w.shape != (len(names),) or not np.isfinite(w).all() or (w < 0).any() or abs(w.sum()-1)>1e-10:
                    raise ValueError("Invalid TARGET weights")
                if w.max() > self.cap+1e-8:
                    raise ValueError("TARGET breaches the sleeve cap")
            if instruction.covariance is not None:
                cov = np.asarray(instruction.covariance, dtype=float)
                if cov.shape != (len(names),len(names)) or not np.isfinite(cov).all():
                    raise ValueError("Instruction covariance must match its sleeve labels")
                if not np.allclose(cov,cov.T,rtol=1e-10,atol=1e-14) or np.linalg.eigvalsh(cov).min() < -1e-12:
                    raise ValueError("Instruction covariance must be symmetric PSD")
                if instruction.reference_variance is None or not np.isfinite(instruction.reference_variance) or instruction.reference_variance <= 0:
                    raise ValueError("Dated forecast diagnostics require positive reference variance")

        def record_trade(date, prices, before, before_shares, before_cash, dollars, cost, reason, signal=None, instruction=None, sizing_residual=0.):
            after = components(prices)
            residual = before["nav"]-after["nav"]-cost
            tol = max(1e-9, before["nav"]*2e-12)
            if abs(residual)>tol or cash < -tol or any(q<0 for q in shares.values()):
                raise ArithmeticError("Trade violated self-financing/nonnegative holdings")
            notional = float(sum(abs(x) for x in dollars.values()))
            row = {"date": date.isoformat(), "signal_date": signal, "reason": reason,
                   "dollars": dollars, "traded_notional": notional, "cost": cost,
                   "pre_nav": before["nav"], "post_nav": after["nav"], "pre_cash": before_cash,
                   "post_cash": cash, "pre_shares": before_shares, "post_shares": shares.copy(),
                   "prices": {n: float(prices[n]) for n in dollars},
                   "self_financing_residual": residual, "sizing_residual": sizing_residual,
                   "routine_turnover": 0. if reason == "initial_entry" else notional/before["nav"],
                   "cost_debit_fraction": cost/before["nav"],
                   "settled_cash_deployed": before_cash-cash,
                   "post_sleeve_weights": list(sleeve_weights(prices)) if after["etf_value"]>0 else None}
            if instruction is not None:
                row["target_weights"] = list(instruction.target_weights)
                row["maximum_target_error"] = float(np.max(np.abs(np.asarray(row["post_sleeve_weights"])-instruction.target_weights)))
                if instruction.covariance is not None:
                    w = np.asarray(row["post_sleeve_weights"])
                    var = float(w @ np.asarray(instruction.covariance) @ w)
                    row["signal_covariance_variance_after_fill"] = var
                    row["signal_covariance_volatility_ratio_after_fill"] = float(np.sqrt(max(0,var)/instruction.reference_variance))
            trades.append(row)
            return before["nav"]/after["nav"]

        def trade_target(date, prices, weights, reason, signal=None, instruction=None):
            nonlocal cash
            before, before_shares, before_cash = components(prices), shares.copy(), cash
            current = np.array([shares[n]*quote(prices,n) for n in names])
            funded = fund_target(current,cash,weights,self.cost_rate)
            dollars = {}
            for n, old, value in zip(names,current,funded.post_values):
                shares[n] = value/quote(prices,n)
                dollars[n] = float(value-old)
            cash = funded.cash
            return record_trade(date,prices,before,before_shares,before_cash,dollars,funded.cost,reason,
                                signal,instruction,funded.funding_residual)

        for date in dates:
            op, cl = tape.opens.loc[date], tape.closes.loc[date]
            day_trades = len(trades)
            removal_factor = 1.
            # Splits change units before distribution entitlements and open orders.
            todays = [a for a in tape.actions if a.ex_date == date]
            for a in sorted(todays, key=lambda a: (a.kind != "split", a.event_id)):
                if a.kind == "split":
                    old = shares[a.ticker]
                    shares[a.ticker] *= a.amount
                    for r in receivables:
                        if r.kind == "in_kind" and r.asset == a.ticker:
                            r.amount *= a.amount
                    events.append({"date": date.isoformat(), "event_id": a.event_id, "phase": "pre_open_split",
                                   "ticker": a.ticker, "old_shares": old, "new_shares": shares[a.ticker]})
                    continue
                if any(r.kind == "in_kind" and r.asset == a.ticker for r in receivables):
                    raise ValueError("Distribution on pending child requires an explicit beneficial-rights review")
                entitlement = shares[a.ticker]*a.amount
                if entitlement > 0:
                    receivables.append(Receivable(a.event_id,a.pay_date,a.kind,entitlement,a.child))
                    events.append({"date": date.isoformat(), "event_id": a.event_id, "phase": "pre_open_accrual",
                                   "kind": a.kind, "amount": entitlement, "asset": a.child,
                                   "pay_date": a.pay_date.isoformat()})
            opening = components(op)
            # Delivered child units are sold at the first subsequent opening.
            for asset in assets:
                if asset in names or shares[asset] == 0:
                    continue
                before, before_shares, before_cash = components(op), shares.copy(), cash
                proceeds = shares[asset]*quote(op,asset)
                cost = self.cost_rate*proceeds
                shares[asset] = 0.
                cash += proceeds-cost
                removal_factor *= record_trade(date,op,before,before_shares,before_cash,{asset:-proceeds},cost,"auxiliary_sale")
            due = queue.pop(date, None)
            if date == start:
                removal_factor *= trade_target(date,op,np.ones(len(names))/len(names),"initial_entry")
            elif due is not None and due["instruction"].action == "TARGET":
                inst = due["instruction"]
                removal_factor *= trade_target(date,op,inst.target_weights,inst.reason,due["signal"]["date"],inst)
            elif cash > max(1e-10, components(op)["nav"]*1e-12):
                removal_factor *= trade_target(date,op,sleeve_weights(op),"cash_reinvestment")
            if due is not None:
                due["signal"]["status"] = "executed" if due["instruction"].action == "TARGET" else "observed_keep"
            # Pay-date close conversion is NAV-neutral; cash is usable next open.
            before_settlement = components(cl)
            for r in list(receivables):
                if r.pay_date <= date:
                    if r.kind == "cash":
                        cash += r.amount
                    else:
                        shares[r.asset] += r.amount
                    receivables.remove(r)
                    events.append({"date": date.isoformat(), "event_id": r.event_id, "phase": "after_close_settlement",
                                   "kind": r.kind, "amount": r.amount, "asset": r.asset})
            closing = components(cl)
            if abs(closing["nav"]-before_settlement["nav"]) > max(1e-9,closing["nav"]*2e-12):
                raise ArithmeticError("Settlement changed NAV")
            weights = sleeve_weights(cl)
            next_date = tape.calendar[tape.calendar.get_loc(date)+1]
            context = CloseContext(date,next_date,names,tuple(weights),closing["nav"],cash,
                                   closing["cash_receivable"]+closing["child_receivable"],
                                   closing["settled_auxiliary"]+closing["child_receivable"],
                                   tape.risk_returns.loc[:date].copy(deep=True))
            try:
                inst = policy(context)
            except Exception as exc:
                # Preserve the exact information set for reproducible solver diagnosis.
                exc.decision_context = {"date": str(date.date()), "tickers": list(context.tickers),
                                        "current_weights": list(context.current_weights)}
                raise
            validate_instruction(inst)
            due_date = tape.calendar[tape.calendar.get_loc(date)+self.lag]
            signal_row = {"date": date.isoformat(), "due_date": due_date.isoformat(), "action": inst.action,
                          "policy": inst.policy, "reason": inst.reason, "current_weights": list(weights),
                          "target_weights": None if inst.target_weights is None else list(inst.target_weights),
                          "diagnostics": inst.diagnostics, "status": "unfilled_at_end"}
            signals.append(signal_row)
            queue[due_date] = {"instruction": inst, "signal": signal_row}
            todays_trades = trades[day_trades:]
            row = {"date": date, **closing, "open_nav_before_trades": opening["nav"],
                   "net_return": closing["nav"]/previous_nav-1,
                   "gross_return": (closing["nav"]/previous_nav)*removal_factor-1,
                   "cost_removal_factor": removal_factor,
                   "total_cost": sum(t["cost"] for t in todays_trades),
                   "entry_cost": sum(t["cost"] for t in todays_trades if t["reason"] == "initial_entry"),
                   "routine_turnover": sum(t["routine_turnover"] for t in todays_trades),
                   "routine_cost_debit_fraction": sum(t["cost_debit_fraction"] for t in todays_trades if t["reason"] != "initial_entry"),
                   "discretionary_trade": any(t["reason"] in {"policy", "cap_repair"} and t["traded_notional"]>max(1e-10,t["pre_nav"]*1e-12) for t in todays_trades),
                   "maximum_sleeve_weight": float(weights.max()),
                   "maximum_etf_nav_weight": float(weights.max()*closing["etf_value"]/closing["nav"]),
                   "cash_fraction": cash/closing["nav"],
                   "receivable_fraction": (closing["cash_receivable"]+closing["child_receivable"])/closing["nav"],
                   "auxiliary_fraction": (closing["settled_auxiliary"]+closing["child_receivable"])/closing["nav"]}
            for n in names:
                row[f"shares_{n}"] = shares[n]
                row[f"weight_{n}"] = float(weights[names.index(n)])
            daily.append(row)
            previous_nav = closing["nav"]
        outstanding = tuple({"event_id":r.event_id,"pay_date":r.pay_date.isoformat(),"kind":r.kind,"amount":r.amount,"asset":r.asset} for r in receivables)
        return SimulationResult(pd.DataFrame(daily).set_index("date"),tuple(trades),tuple(signals),tuple(events),outstanding,shares.copy(),cash)
