from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import project_runtime
import numpy as np
import pandas as pd
from risk_rebalancing.experiments import policy_grid
from risk_rebalancing.selection import ABS_TOL, PRIMARY, TURN, VOL, select_comparators

def fixture_rows():
    return [{"id": n, VOL: .1, TURN: 2.} for n, _ in policy_grid()]


def change(rows, name, **kwargs):
    next(r for r in rows if r["id"] == name).update(kwargs)


class SelectionTests(unittest.TestCase):
    def test_primary_fixed_exclusions_and_fixed_tie_order(self):
        rows = fixture_rows()
        change(rows, "equal_weight_monthly", **{TURN: 0.})
        change(rows, "risk_tolerant_0.05", **{TURN: 0.})
        result = select_comparators(rows)
        self.assertEqual(result["primary_A"], PRIMARY)
        self.assertEqual(result["primary_B"], "minimum_variance_monthly")
        self.assertEqual(result, select_comparators(list(reversed(rows))))

    def test_risk_ceiling_rejects_cheap_high_risk_candidate(self):
        rows = fixture_rows()
        change(rows, "minimum_variance_monthly", **{TURN: 0., VOL: .10201})
        change(rows, "weight_band_0.01", **{TURN: .5, VOL: .102})
        result = select_comparators(rows)
        self.assertEqual(result["primary_B"], "weight_band_0.01")
        self.assertNotIn("minimum_variance_monthly", result["eligible_conventional_ids"])

    def test_turnover_tie_then_risk_then_fixed_order(self):
        rows = fixture_rows()
        change(rows, "minimum_variance_monthly", **{TURN: .5 + ABS_TOL/2, VOL: .101})
        change(rows, "minimum_variance_weekly", **{TURN: .5, VOL: .1})
        self.assertEqual(select_comparators(rows)["primary_B"], "minimum_variance_weekly")

    def test_matched_selects_risk_before_turnover_or_parameter(self):
        rows = fixture_rows()
        change(rows, PRIMARY, **{TURN: 1.})
        change(rows, "weight_band_0.0025", **{TURN: .9, VOL: .1})
        change(rows, "weight_band_0.005", **{TURN: 1.1, VOL: .099})
        result = select_comparators(rows)["secondary"]["weight_band"]
        self.assertTrue(result["matched"])
        self.assertEqual(result["id"], "weight_band_0.005")

    def test_unmatched_minimizes_distance_then_risk(self):
        rows = fixture_rows()
        change(rows, PRIMARY, **{TURN: 1.})
        change(rows, "variance_penalty_0.01", **{TURN: .5, VOL: .1})
        change(rows, "variance_penalty_0.03", **{TURN: 1.5, VOL: .09})
        result = select_comparators(rows)["secondary"]["variance_penalty"]
        self.assertFalse(result["matched"])
        self.assertEqual(result["id"], "variance_penalty_0.03")

    def test_secondary_ties_choose_smaller_parameter(self):
        result = select_comparators(fixture_rows())["secondary"]
        self.assertEqual(result["weight_band"]["id"], "weight_band_0.0025")
        self.assertEqual(result["variance_penalty"]["id"], "variance_penalty_0.01")

    def test_zero_primary_turnover_has_explicit_matching_rule(self):
        rows = fixture_rows()
        change(rows, PRIMARY, **{TURN: 0.})
        change(rows, "weight_band_0.01", **{TURN: 0.})
        result = select_comparators(rows)["secondary"]
        self.assertTrue(result["weight_band"]["matched"])
        self.assertIsNone(result["weight_band"]["relative_turnover_distance"])
        self.assertFalse(result["variance_penalty"]["matched"])

    def test_incomplete_duplicate_invalid_metric_sets_rejected(self):
        rows = fixture_rows()
        for bad in (rows[:-1], rows + [rows[0]], [{**r, VOL: float("nan")} for r in rows],
                    [{**r, TURN: -1} for r in rows], [{**r, VOL: 0.} for r in rows]):
            with self.subTest(bad=bad[0]), self.assertRaises(ValueError):
                select_comparators(bad)
