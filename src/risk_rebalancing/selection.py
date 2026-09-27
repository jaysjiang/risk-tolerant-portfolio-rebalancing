"""Pure, deterministic implementation of the prespecified validation selection."""
import math
from .experiments import BANDS, PENALTIES, policy_grid

PRIMARY = "risk_tolerant_0.02"
VOL = "annualized_gross_volatility"
TURN = "annualized_full_notional_turnover"
ABS_TOL = 1e-10
RATIO_TOL = 1e-10
CONVENTIONAL = (
    "minimum_variance_monthly", "minimum_variance_weekly", "minimum_variance_daily",
    *(f"weight_band_{x:g}" for x in BANDS),
    *(f"variance_penalty_{x:g}" for x in PENALTIES),
)


def _minimum_ties(candidates, value):
    best = min(value(c) for c in candidates)
    return [c for c in candidates if value(c) <= best + ABS_TOL]


def select_comparators(rows):
    """All and only the original 21 rows are required; input order is irrelevant."""
    names = [r["id"] for r in rows]
    if len(names) != len(set(names)) or set(names) != {n for n, _ in policy_grid()}:
        raise ValueError("Selection requires exactly the 21 frozen configurations")
    values = {r["id"]: r for r in rows}
    for row in rows:
        if (not math.isfinite(row[VOL]) or row[VOL] <= 0
                or not math.isfinite(row[TURN]) or row[TURN] < 0):
            raise ValueError("Selection requires positive finite volatility and nonnegative finite turnover")
    reference = values["minimum_variance_daily"][VOL]
    eligible = [n for n in CONVENTIONAL if values[n][VOL] / reference <= 1.02 + RATIO_TOL]
    finalists = _minimum_ties(eligible, lambda n: values[n][TURN])
    finalists = _minimum_ties(finalists, lambda n: values[n][VOL])
    selected = finalists[0]  # already in fixed protocol order
    primary_turn = values[PRIMARY][TURN]
    secondary = {}
    for family, parameters in (("weight_band", BANDS), ("variance_penalty", PENALTIES)):
        candidates = [f"{family}_{p:g}" for p in parameters]
        distances = {n: abs(values[n][TURN] - primary_turn) for n in candidates}
        matched = [n for n in candidates if (distances[n] <= ABS_TOL if primary_turn == 0
                   else distances[n] / primary_turn <= .10 + RATIO_TOL)]
        finalists = matched or _minimum_ties(candidates, lambda n: distances[n])
        finalists = _minimum_ties(finalists, lambda n: values[n][VOL])
        finalists = _minimum_ties(finalists, lambda n: values[n][TURN])
        chosen = finalists[0]  # ascending parameters
        secondary[family] = {
            "id": chosen, "matched": bool(matched), "qualifying_ids": matched,
            "turnover_distance": distances[chosen],
            "relative_turnover_distance": distances[chosen] / primary_turn if primary_turn else None,
            "volatility": values[chosen][VOL], "turnover": values[chosen][TURN],
        }
    return {
        "primary_A": PRIMARY, "primary_B": selected,
        "volatility_ceiling": 1.02 * reference, "daily_mv_volatility": reference,
        "absolute_tie_tolerance": ABS_TOL, "ratio_boundary_tolerance": RATIO_TOL,
        "eligible_conventional_ids": eligible,
        "conventional_audit": [{"id": n, "volatility": values[n][VOL], "turnover": values[n][TURN],
                                "volatility_ratio_to_daily_mv": values[n][VOL] / reference,
                                "eligible": n in eligible} for n in CONVENTIONAL],
        "secondary": secondary,
    }
