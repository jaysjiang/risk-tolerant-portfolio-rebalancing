"""Paired stationary-bootstrap inference on recorded, frozen policy outcomes."""
import hashlib
import numpy as np


def stationary_indices(n, replications=5000, mean_block=20, seed=20260926):
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise ValueError("At least two observations required")
    if not isinstance(replications, int) or replications < 1 or not np.isfinite(mean_block) or mean_block < 1:
        raise ValueError("Invalid bootstrap replication count or block length")
    rng = np.random.Generator(np.random.PCG64(seed))
    indices = rng.integers(0, n, size=(replications, n), dtype=np.int32)
    uniforms = rng.random((replications, n))
    for t in range(1, n):
        indices[:, t] = np.where(uniforms[:, t] > 1 / mean_block, (indices[:, t-1] + 1) % n, indices[:, t])
    return indices


def _data(values):
    data = np.asarray(values, dtype=float)
    if data.ndim != 2 or data.shape[1] != 4 or len(data) < 2 or not np.isfinite(data).all():
        raise ValueError("Expected finite aligned Nx4 returns/turnover records")
    if (data[:, :2] <= -1).any() or (data[:, 2:] < 0).any():
        raise ValueError("Invalid return or negative turnover")
    return data


def effects(values):
    data = _data(values)
    volatility = data[:, :2].std(axis=0, ddof=1) * np.sqrt(252)
    turnover = data[:, 2:].mean(axis=0) * 252
    return {"sessions": len(data), "volatility_A": float(volatility[0]), "volatility_B": float(volatility[1]),
            "turnover_A": float(turnover[0]), "turnover_B": float(turnover[1]),
            "volatility_ratio": float(volatility[0]/volatility[1]) if volatility[1] > 0 else None,
            "turnover_ratio": float(turnover[0]/turnover[1]) if turnover[1] > 0 else None}


def classify(point, intervals):
    names = ("volatility_ratio", "turnover_ratio")
    thresholds = (1.02, .80)
    defined = all(point[n] is not None and intervals[n]["undefined_replications"] == 0 for n in names)
    if not defined:
        return {"classification": "Undefined statistic: no significance claim", "strong_support": False,
                "evidence_against": False, "point_estimates_meet_target": None}
    point_ok = all(point[n] <= t for n, t in zip(names, thresholds))
    upper_ok = all(intervals[n]["simultaneous_upper"] <= t for n, t in zip(names, thresholds))
    against = any(intervals[n]["simultaneous_lower"] > t for n, t in zip(names, thresholds))
    label = ("Strong support" if upper_ok else "Promising but uncertain" if point_ok else "Primary target not established")
    return {"classification": label, "strong_support": upper_ok, "evidence_against": against,
            "point_estimates_meet_target": point_ok}


def paired_bootstrap(values, replications=5000, mean_block=20, seed=20260926):
    data = _data(values)
    indices = stationary_indices(len(data), replications, mean_block, seed)
    draws = np.full((replications, 2), np.nan)
    for first in range(0, replications, 250):
        sampled = data[indices[first:first+250]]
        vol = sampled[:, :, :2].std(axis=1, ddof=1)
        turn = sampled[:, :, 2:].mean(axis=1)
        np.divide(vol[:, 0], vol[:, 1], out=draws[first:first+250, 0], where=vol[:, 1] > 0)
        np.divide(turn[:, 0], turn[:, 1], out=draws[first:first+250, 1], where=turn[:, 1] > 0)
    intervals = {}
    for i, name in enumerate(("volatility_ratio", "turnover_ratio")):
        undefined = int((~np.isfinite(draws[:, i])).sum())
        bounds = [None, None] if undefined else np.quantile(draws[:, i], [.025, .975], method="linear").tolist()
        intervals[name] = {"point": effects(data)[name], "percentile_95": bounds,
                           "simultaneous_lower": bounds[0], "simultaneous_upper": bounds[1],
                           "undefined_replications": undefined}
    point = effects(data)
    return {"replications": replications, "mean_block": mean_block, "seed": seed, "rng": "PCG64",
            "index_array_sha256": hashlib.sha256(indices.tobytes(order="C")).hexdigest(),
            "paired_fields": ["gross_A", "gross_B", "turnover_A", "turnover_B"],
            "point": point, "intervals": intervals, **classify(point, intervals)}, draws


def stability(values, dates):
    data = _data(values)
    years = np.array([date.year for date in dates])
    if len(years) != len(data):
        raise ValueError("Dates and outcomes are not aligned")
    periods = [(str(y), years == y) for y in range(2020, 2026)]
    periods += [(f"{y}–{y+1}", (years >= y) & (years <= y+1)) for y in (2020, 2022, 2024)]
    periods += [(f"Excluding {y}", years != y) for y in range(2020, 2026)]
    return [{"period": name, **effects(data[mask])} for name, mask in periods if mask.sum() >= 2]
