"""After-close policy adapter; all calendar policies monitor sleeve caps daily."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .ledger import CloseContext, Instruction
from .optimization import PortfolioOptimizer
from .risk import estimate_covariance


def calendar_due(date, next_session, frequency):
    if next_session <= date:
        raise ValueError("Next session must follow the decision date")
    if frequency == "daily":
        return True
    if frequency == "weekly":
        return date.to_period("W-SUN") != next_session.to_period("W-SUN")
    if frequency == "monthly":
        return (date.year,date.month) != (next_session.year,next_session.month)
    raise ValueError("Unknown calendar frequency")


@dataclass(frozen=True)
class PortfolioPolicy:
    kind: str = "risk_tolerant"
    frequency: str = "daily"
    epsilon: float = .02
    band: float = .01
    penalty: float = 1.
    cap: float = .25
    window: int = 252
    estimator: str = "ledoit_wolf"

    def __post_init__(self):
        if not np.isfinite(self.cap) or not 0 < self.cap <= 1:
            raise ValueError("Policy cap must be finite and in (0,1]")
        if self.kind not in {"risk_tolerant","minimum_variance","equal_weight","weight_band","variance_penalty"}:
            raise ValueError("Unknown portfolio policy")
        if self.frequency not in {"daily","weekly","monthly"}:
            raise ValueError("Unknown calendar frequency")
        if self.kind in {"risk_tolerant","weight_band","variance_penalty"} and self.frequency != "daily":
            raise ValueError("Tolerance, band and penalty policies have daily decisions")
        if self.kind == "equal_weight" and self.frequency != "monthly":
            raise ValueError("The prespecified equal-weight reference is monthly")
        for value in (self.epsilon,self.band,self.penalty):
            if not np.isfinite(value) or value < 0:
                raise ValueError("Policy parameters must be finite and nonnegative")

    def __call__(self, context: CloseContext):
        current = pd.Series(context.current_weights,index=context.tickers)
        if self.cap*len(current) < 1-1e-12:
            raise ValueError("Infeasible policy cap")
        due = calendar_due(context.date,context.next_session,self.frequency)
        breached = current.max() > self.cap+1e-8
        # Fit every day, even on calendar KEEP dates, so missing risk inputs cannot
        # pass unnoticed and identical dated reference diagnostics are available.
        estimate = estimate_covariance(context.risk_returns,context.date,self.window,self.estimator)
        opt = PortfolioOptimizer(estimate.covariance_frame(),cap=self.cap)
        reference = opt.minimum_variance()
        reason = "policy"
        if not due:
            if breached:
                decision = opt.repair_caps(current)
                reason = "cap_repair"
            else:
                decision = None
        elif self.kind == "minimum_variance":
            decision = opt.minimum_variance_target(current)
        elif self.kind == "risk_tolerant":
            decision = opt.risk_tolerant(current,self.epsilon)
        elif self.kind == "weight_band":
            decision = opt.weight_band(current,self.band)
        elif self.kind == "variance_penalty":
            decision = opt.variance_penalty(current,self.penalty)
        else:
            decision = None
        diag = {"as_of":context.date.isoformat(),"window_start":estimate.window_start.isoformat(),
                "window_end":estimate.window_end.isoformat(),"observations":estimate.observations,
                "calendar_due":due,"cap_breached_at_close":bool(breached),
                "current_sleeve_forecast_variance":float(current.to_numpy() @ estimate.covariance_frame().to_numpy() @ current.to_numpy()),
                "reference_variance_daily":reference.variance_daily,
                "reference_diagnostics":reference.diagnostics}
        if self.kind == "equal_weight" and due:
            action, target = "TARGET", tuple(np.ones(len(current))/len(current))
        elif decision is None:
            action, target = "KEEP", None
        else:
            action, target = decision.action, decision.target_weights
            diag["optimizer"] = decision.to_dict()
        return Instruction(action,target,reason,f"{self.kind}_{self.frequency}",diag,
                           estimate.covariance_values,reference.variance_daily)
