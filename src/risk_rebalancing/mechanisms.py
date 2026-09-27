"""Exploratory descriptive accounting; does not select or modify policies."""
import numpy as np


def finite_vector(values, *, nonnegative=False):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all():
        raise ValueError("Expected a nonempty finite vector")
    if nonnegative and (x < 0).any():
        raise ValueError("Expected nonnegative observations")
    return x


def turnover_decomposition(values):
    q = finite_vector(values, nonnegative=True)
    active = q > 0
    frequency = float(active.mean())
    size = float(q[active].mean()) if active.any() else 0.
    annual = float(252*q.mean())
    if not np.isclose(annual, 252*frequency*size, rtol=1e-12, atol=1e-14):
        raise ValueError("Frequency/size identity failed")
    return {"sessions": len(q), "active_days": int(active.sum()), "active_fraction": frequency,
            "mean_turnover_active_day": size, "annual_turnover": annual}


def variance_contributions(a, b, labels):
    a, b = finite_vector(a), finite_vector(b)
    labels = np.asarray(labels)
    if len(a) != len(b) or len(a) != len(labels) or len(a) < 2:
        raise ValueError("Aligned series with at least two observations required")
    daily = 252*((a-a.mean())**2-(b-b.mean())**2)/(len(a)-1)
    rows = [{"period": str(label), "sessions": int((labels==label).sum()),
             "annual_variance_difference_contribution": float(daily[labels==label].sum())}
            for label in np.unique(labels)]
    total = float(252*(a.var(ddof=1)-b.var(ddof=1)))
    if not np.isclose(sum(r["annual_variance_difference_contribution"] for r in rows), total, rtol=1e-10, atol=1e-14):
        raise ValueError("Variance attribution identity failed")
    return {"total_annual_variance_difference": total, "periods": rows}


def exposure_projection(returns, reference):
    y, x = finite_vector(returns), finite_vector(reference)
    if len(x) != len(y) or len(x)<2 or x.var(ddof=1) == 0:
        raise ValueError("Projection needs aligned variable reference")
    beta = float(np.dot(x-x.mean(), y-y.mean())/np.dot(x-x.mean(), x-x.mean()))
    intercept = float(y.mean()-beta*x.mean())
    residual = y-intercept-beta*x
    explained = float(beta**2*x.var(ddof=1)*252)
    unexplained = float(residual.var(ddof=1)*252)
    total = float(y.var(ddof=1)*252)
    if not np.isclose(explained+unexplained, total, rtol=1e-11, atol=1e-14):
        raise ValueError("OLS variance identity failed")
    return {"beta_to_monthly_equal_weight": beta, "intercept_daily_descriptive_only": intercept,
            "reference_component_annual_variance": explained, "residual_annual_variance": unexplained,
            "residual_annual_volatility": float(np.sqrt(unexplained)), "total_annual_variance": total,
            "r_squared": explained/total if total>0 else None}


def largest_share(values, k):
    x = finite_vector(values, nonnegative=True)
    if not isinstance(k,int) or k<1:
        raise ValueError("Positive integer rank count required")
    return float(np.sort(x)[-k:].sum()/x.sum()) if x.sum()>0 else None


def trigger_category(signal, epsilon=.02):
    d = signal["diagnostics"]
    cap = bool(d["cap_breached_at_close"])
    risk = d["current_sleeve_forecast_variance"] > d["reference_variance_daily"]*(1+epsilon)**2*(1+1e-7)
    return "both" if cap and risk else "cap_only" if cap else "risk_only" if risk else "neither"


def empirical_dominators(rows, primary, tolerance=1e-12):
    target = next(r for r in rows if r["id"]==primary)
    keys = ("annualized_gross_volatility", "annualized_full_notional_turnover")
    return [r["id"] for r in rows if r["id"]!=primary
            and all(r[k]<=target[k]+tolerance for k in keys)
            and any(r[k]<target[k]-tolerance for k in keys)]
