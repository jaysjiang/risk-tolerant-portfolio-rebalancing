"""Trailing covariance estimates with an explicit after-close information cutoff."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf


@dataclass(frozen=True)
class RiskEstimate:
    tickers: tuple[str, ...]
    as_of_session: pd.Timestamp
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    observations: int
    estimator: str
    shrinkage: float | None
    covariance_values: tuple[tuple[float, ...], ...]

    def covariance_frame(self) -> pd.DataFrame:
        """A fresh daily covariance frame; callers cannot mutate this estimate."""
        return pd.DataFrame(self.covariance_values, index=self.tickers, columns=self.tickers)


def estimate_covariance(returns: pd.DataFrame, as_of_session, window=252,
                        estimator="ledoit_wolf") -> RiskEstimate:
    """Use the last `window` rows through the named session's close.

    Returns must be simple total returns in fractions on a complete session grid.
    The data pipeline validates that grid. Missing cells inside the selected
    window raise; they are never filled or skipped to reach farther into history.
    Intraday availability and execution are outside this function's contract.
    """
    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError("returns must be a nonempty labeled DataFrame")
    if not isinstance(window, int) or isinstance(window, bool) or window < 2:
        raise ValueError("window must be an integer >= 2")
    index = returns.index
    if (not isinstance(index, pd.DatetimeIndex) or index.tz is not None or
            index.has_duplicates or not index.is_monotonic_increasing or
            not index.equals(index.normalize()) or index.hasnans):
        raise ValueError("index must contain unique sorted timezone-free session dates")
    labels = tuple(returns.columns)
    if len(labels) < 2 or len(set(labels)) != len(labels) or not all(isinstance(x,str) and x for x in labels):
        raise ValueError("asset labels must be unique nonempty strings")
    as_of = pd.Timestamp(as_of_session)
    if pd.isna(as_of) or as_of.tz is not None or as_of != as_of.normalize() or as_of not in index:
        raise ValueError("as_of_session must be a session-date label present in returns")
    history = returns.loc[:as_of].tail(window)
    if len(history) != window:
        raise ValueError(f"Need {window} trailing observations; have {len(history)}")
    try:
        values = history.to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError("selected return window must be numeric") from exc
    if not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("selected return window contains missing, nonfinite or <= -100% returns")
    shrinkage = None
    if estimator in ("ledoit_wolf", "diagonal_ledoit_wolf"):
        fitted = LedoitWolf(assume_centered=False, store_precision=False).fit(values)
        covariance = fitted.covariance_
        shrinkage = float(fitted.shrinkage_)
        if estimator == "diagonal_ledoit_wolf":
            covariance = np.diag(np.diag(covariance))
    elif estimator == "sample":
        covariance = np.cov(values, rowvar=False, ddof=1)
    else:
        raise ValueError(f"Unsupported prespecified estimator: {estimator}")
    if not np.isfinite(covariance).all() or float(np.trace(covariance)) <= 0:
        raise ValueError("Covariance is nonfinite or has zero total variance")
    return RiskEstimate(labels, as_of, history.index[0], history.index[-1], window,
                        estimator, shrinkage, tuple(tuple(float(x) for x in row) for row in covariance))
