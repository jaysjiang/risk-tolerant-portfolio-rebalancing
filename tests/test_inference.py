from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import project_runtime
import numpy as np
import pandas as pd
from risk_rebalancing.inference import classify, effects, paired_bootstrap, stability, stationary_indices

class InferenceTests(unittest.TestCase):
    def test_circular_continuation_and_restart_hand_example(self):
        fake = SimpleNamespace(integers=lambda *a, **k: np.array([[4, 3, 3, 4, 2]], dtype=np.int32),
                               random=lambda *a: np.array([[0., .9, .9, 0., .9]]))
        with patch("risk_rebalancing.inference.np.random.Generator", return_value=fake):
            result = stationary_indices(5, 1, 2)
        np.testing.assert_array_equal(result, [[4, 0, 1, 4, 0]])

    def test_paired_sampling_preserves_exact_scaled_ratios(self):
        rng = np.random.default_rng(17)
        r = rng.normal(0, .005, 250)
        turn = rng.uniform(.001, .05, 250)
        data = np.column_stack([1.01*r, r, .6*turn, turn])
        summary, draws = paired_bootstrap(data, replications=60)
        np.testing.assert_allclose(draws[:, 0], 1.01, atol=1e-12)
        np.testing.assert_allclose(draws[:, 1], .6, atol=1e-12)
        self.assertTrue(summary["strong_support"])
        self.assertFalse(summary["evidence_against"])
        again, repeated = paired_bootstrap(data, replications=60)
        self.assertEqual(summary, again)
        np.testing.assert_array_equal(draws, repeated)

    def test_denominator_failures_preserved_and_withhold_significance(self):
        data = np.column_stack([np.arange(20)*.001, np.arange(20)*.001, np.ones(20), np.zeros(20)])
        summary, draws = paired_bootstrap(data, replications=25)
        self.assertEqual(summary["intervals"]["turnover_ratio"]["undefined_replications"], 25)
        self.assertEqual(summary["intervals"]["turnover_ratio"]["percentile_95"], [None, None])
        self.assertIsNone(summary["point"]["turnover_ratio"])
        self.assertTrue(np.isnan(draws[:, 1]).all())
        self.assertFalse(summary["strong_support"])

    def test_effects_match_hand_arithmetic(self):
        data = [[-.01, -.02, .1, .2], [.01, .02, .2, .4], [0., 0., 0., 0.]]
        result = effects(data)
        self.assertAlmostEqual(result["volatility_ratio"], .5)
        self.assertAlmostEqual(result["turnover_ratio"], .5)
        self.assertAlmostEqual(result["turnover_A"], 25.2)
        self.assertAlmostEqual(result["volatility_A"], .01*np.sqrt(252))

    def test_point_support_is_not_confidence_support(self):
        point = {"volatility_ratio": 1.01, "turnover_ratio": .7}
        intervals = {"volatility_ratio": {"undefined_replications": 0, "simultaneous_lower": .95, "simultaneous_upper": 1.04},
                     "turnover_ratio": {"undefined_replications": 0, "simultaneous_lower": .6, "simultaneous_upper": .9}}
        self.assertEqual(classify(point, intervals)["classification"], "Promising but uncertain")
        point["turnover_ratio"] = 1.2
        intervals["turnover_ratio"]["simultaneous_lower"] = 1.1
        result = classify(point, intervals)
        self.assertEqual(result["classification"], "Primary target not established")
        self.assertTrue(result["evidence_against"])

    def test_invalid_inputs_do_not_silently_drop_dates(self):
        for data in ([[0., 0., 0., 0.]], [[0., 0., 0., 0.], [np.nan, 0., 0., 0.]],
                     [[0., 0., 0., 0.], [0., 0., -1., 0.]]):
            with self.assertRaises(ValueError): effects(data)
        for args in ((1, 20, 20), (5, 0, 20), (5, 20, 0)):
            with self.assertRaises(ValueError): stationary_indices(*args)

    def test_prespecified_stability_periods_use_original_slices(self):
        dates = pd.date_range("2020-01-01", "2025-12-31", freq="MS")
        x = np.linspace(-.01, .02, len(dates))
        result = stability(np.column_stack([x, x, np.ones(len(x)), np.ones(len(x))]), dates)
        self.assertEqual(len(result), 15)
        self.assertEqual(result[0]["sessions"], 12)
        self.assertEqual(result[6]["sessions"], 24)
        self.assertEqual(result[-1]["sessions"], 60)
        self.assertTrue(all(np.isclose(r["volatility_ratio"], 1) for r in result))
