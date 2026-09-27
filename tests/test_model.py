"""Analytic examples, convex certificates, invariants and information cutoffs."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import project_runtime  # noqa: F401
import cvxpy as cp
import numpy as np
import pandas as pd
from risk_rebalancing.risk import estimate_covariance
from risk_rebalancing.optimization import PortfolioOptimizer, OptimizationError

LABELS = tuple(f"A{i}" for i in range(9))


def covariance(matrix):
    return pd.DataFrame(matrix,index=LABELS,columns=LABELS)


def current(values=None):
    return pd.Series(np.ones(9)/9 if values is None else values,index=LABELS)


def optimizer():
    return PortfolioOptimizer(covariance(np.diag(np.arange(1,10))*1e-4))


class RiskModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(20260926)
        cls.returns = pd.DataFrame(rng.normal(0,.01,(800,9)),
                                  index=pd.bdate_range("2010-01-01",periods=800),columns=LABELS)

    def test_window_and_information_cutoff(self):
        result = estimate_covariance(self.returns,self.returns.index[400])
        self.assertEqual(result.observations,252)
        self.assertEqual(result.window_end,self.returns.index[400])
        self.assertEqual(result.window_start,self.returns.index[149])
        self.assertGreaterEqual(result.shrinkage,0)
        self.assertLessEqual(result.shrinkage,1)

    def test_future_values_do_not_change_earlier_estimate_or_decision(self):
        changed = self.returns.copy()
        changed.iloc[401:,:] = np.nan
        first = estimate_covariance(self.returns,self.returns.index[400])
        second = estimate_covariance(changed,self.returns.index[400])
        self.assertEqual(first,second)
        a = PortfolioOptimizer(first.covariance_frame()).risk_tolerant(current())
        b = PortfolioOptimizer(second.covariance_frame()).risk_tolerant(current())
        self.assertEqual(a.action,b.action)
        self.assertEqual(a.target_weights,b.target_weights)

    def test_missing_in_window_is_rejected_not_skipped(self):
        values = self.returns.copy()
        values.iloc[399,0] = np.nan
        with self.assertRaisesRegex(ValueError,"missing"):
            estimate_covariance(values,values.index[400])

    def test_before_window_changes_have_no_effect(self):
        values = self.returns.copy()
        values.iloc[:149] = 10.
        self.assertEqual(estimate_covariance(values,values.index[400]),estimate_covariance(self.returns,values.index[400]))

    def test_sample_covariance_matches_manual_centering(self):
        result = estimate_covariance(self.returns,self.returns.index[400],126,"sample")
        x = self.returns.iloc[275:401].to_numpy()
        centered = x-x.mean(axis=0)
        np.testing.assert_allclose(result.covariance_frame(),centered.T@centered/125,rtol=1e-12)

    def test_diagonal_sensitivity_uses_same_marginal_variances(self):
        full = estimate_covariance(self.returns,self.returns.index[700],504)
        diagonal = estimate_covariance(self.returns,self.returns.index[700],504,"diagonal_ledoit_wolf")
        np.testing.assert_array_equal(np.diag(full.covariance_frame()),np.diag(diagonal.covariance_frame()))
        self.assertEqual(np.count_nonzero(diagonal.covariance_frame()),9)

    def test_short_history_and_invalid_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"trailing"):
            estimate_covariance(self.returns,self.returns.index[100])
        for data, date in [(self.returns.iloc[::-1],self.returns.index[400]),
                           (self.returns,self.returns.index[400]+pd.Timedelta(hours=16))]:
            with self.subTest(date=date),self.assertRaises(ValueError):
                estimate_covariance(data,date)

    def test_constant_panel_is_not_given_an_artificial_risk_floor(self):
        with self.assertRaisesRegex(ValueError,"zero"):
            estimate_covariance(self.returns*0,self.returns.index[400])


class OptimizerTests(unittest.TestCase):
    def assert_feasible(self, result, opt):
        x = np.asarray(result.target_weights if result.action=="TARGET" else result.current_weights)
        self.assertAlmostEqual(x.sum(),1,places=8)
        self.assertGreaterEqual(x.min(),-1e-8)
        self.assertLessEqual(x.max(),opt.cap+1e-8)
        if result.risk_limit_daily is not None:
            self.assertLessEqual(result.forecast_variance_daily,result.risk_limit_daily*(1+1e-7))

    def test_diagonal_solution_matches_capped_inverse_variance(self):
        opt = optimizer()
        result = opt.minimum_variance()
        # First asset reaches 25%; remaining 75% is inverse-variance allocated.
        expected = np.r_[.25, .75/(np.arange(2,10)*sum(1/np.arange(2,10)))]
        np.testing.assert_allclose(result.weights,expected,atol=2e-6,rtol=0)
        exact = float(np.sum(expected**2*np.arange(1,10))*1e-4)
        self.assertLessEqual(result.lower_bound_daily,exact+1e-14)
        self.assertGreaterEqual(result.variance_daily,exact-1e-14)

    def test_feasible_current_is_exact_keep_with_no_target(self):
        opt = optimizer()
        state = current(opt.minimum_variance().weights)
        result = opt.risk_tolerant(state,.02)
        self.assertEqual(result.action,"KEEP")
        self.assertIsNone(result.target_weights)
        self.assertEqual(result.expected_weight_turnover,0)
        np.testing.assert_array_equal(result.current_weights,state.to_numpy())

    def test_relative_volatility_tolerance_is_squared_for_variance(self):
        opt = optimizer()
        result = opt.risk_tolerant(current(),.02)
        self.assertAlmostEqual(result.risk_limit_daily/opt.minimum_variance().variance_daily,1.02**2)
        self.assert_feasible(result,opt)

    def test_zero_tolerance_matches_unique_minimum(self):
        opt = optimizer()
        result = opt.risk_tolerant(current(),0)
        np.testing.assert_array_equal(result.target_weights,opt.minimum_variance().weights)
        self.assert_feasible(result,opt)

    def test_singular_covariance_preserves_optimal_current(self):
        opt = PortfolioOptimizer(covariance(np.ones((9,9))*1e-4))
        result = opt.risk_tolerant(current(),0)
        self.assertEqual(result.action,"KEEP")
        self.assertEqual(opt.rank,1)

    def test_singular_zero_tolerance_cap_repair(self):
        opt = PortfolioOptimizer(covariance(np.ones((9,9))*1e-4))
        result = opt.risk_tolerant(current([.4]+[.075]*8),0)
        self.assertEqual(result.action,"TARGET")
        self.assertAlmostEqual(result.expected_weight_turnover,.3,places=6)
        self.assert_feasible(result,opt)

    def test_fixed_state_turnover_decreases_with_tolerance(self):
        opt = optimizer()
        results = [opt.risk_tolerant(current(),epsilon) for epsilon in [0,.01,.02,.05]]
        turns = [x.expected_weight_turnover for x in results]
        self.assertTrue(np.all(np.diff(turns)<=1e-6),turns)
        for result in results:
            self.assert_feasible(result,opt)

    def test_risk_solution_is_partial_and_turnover_bound_is_certified(self):
        opt = optimizer()
        result = opt.risk_tolerant(current(),.02)
        full = opt.minimum_variance_target(current())
        self.assertGreater(result.expected_weight_turnover,0)
        self.assertLess(result.expected_weight_turnover,full.expected_weight_turnover)
        self.assertLessEqual(result.diagnostics["tie_break"]["primary_gap_upper_bound"],3.1e-7)

    def test_uniform_scaling_covariance_preserves_target(self):
        a = optimizer().risk_tolerant(current(),.02)
        b = PortfolioOptimizer(covariance(np.diag(np.arange(1,10))*1e4)).risk_tolerant(current(),.02)
        np.testing.assert_allclose(a.target_weights,b.target_weights,atol=1e-6,rtol=0)
        self.assertAlmostEqual(a.expected_weight_turnover,b.expected_weight_turnover,places=7)

    def test_two_asset_risk_boundary_matches_closed_form(self):
        labels = ["low","high"]
        frame = pd.DataFrame(np.diag([1.,4.])*1e-4,index=labels,columns=labels)
        opt = PortfolioOptimizer(frame,cap=1.)
        result = opt.risk_tolerant(pd.Series([.2,.8],index=labels),.02)
        # q(w)=5*(w-.8)^2+.8; nearest feasible point to w=.2 is its lower root.
        root = .8-np.sqrt(.8*(1.02**2-1)/5)
        exact_turnover = 2*(root-.2)
        np.testing.assert_allclose(result.target_weights,[root,1-root],atol=2e-7,rtol=0)
        self.assertLessEqual(result.diagnostics["primary"]["lower_bound"],exact_turnover+1e-9)
        self.assertAlmostEqual(result.expected_weight_turnover,exact_turnover,places=6)

    def test_position_cap_is_checked_even_under_large_risk_tolerance(self):
        opt = optimizer()
        result = opt.risk_tolerant(current([.4]+[.075]*8),100)
        self.assertEqual(result.action,"TARGET")
        self.assert_feasible(result,opt)

    def test_cap_repair_has_analytic_l1_cost_and_distance_tie_break(self):
        opt = optimizer()
        result = opt.repair_caps(current([.4]+[.075]*8))
        self.assertAlmostEqual(result.expected_weight_turnover,.3,places=6)
        np.testing.assert_allclose(result.target_weights,[.25]+[.09375]*8,atol=2e-6,rtol=0)

    def test_band_policy_is_partial_and_zero_band_matches_reference(self):
        opt = optimizer()
        result = opt.weight_band(current(),.02)
        self.assert_feasible(result,opt)
        self.assertLessEqual(np.max(np.abs(np.asarray(result.target_weights)-opt.minimum_variance().weights)),.02000001)
        zero = opt.weight_band(current(),0)
        np.testing.assert_allclose(zero.target_weights,opt.minimum_variance().weights,atol=2e-8,rtol=0)
        self.assertEqual(opt.weight_band(current(),1).action,"KEEP")

    def test_penalty_zero_matches_reference_and_large_penalty_can_keep(self):
        opt = optimizer()
        zero = opt.variance_penalty(current(),0)
        np.testing.assert_array_equal(zero.target_weights,opt.minimum_variance().weights)
        self.assertEqual(opt.variance_penalty(current(),10).action,"KEEP")
        partial = opt.variance_penalty(current(),.1)
        self.assert_feasible(partial,opt)
        self.assertLessEqual(partial.diagnostics["primary"]["absolute_gap"],2e-7)

    def test_current_labels_align_without_positional_mismatch(self):
        opt = optimizer()
        first = opt.risk_tolerant(current(),.02)
        second = opt.risk_tolerant(current().iloc[::-1],.02)
        np.testing.assert_array_equal(first.target_weights,second.target_weights)

    def test_bad_covariance_or_infeasible_caps_raise(self):
        for matrix,cap in [(np.eye(9),.1),(-np.eye(9),.25),(np.zeros((9,9)),.25),
                           (np.eye(9)+np.triu(np.ones((9,9)),1),.25)]:
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                PortfolioOptimizer(covariance(matrix),cap=cap)

    def test_cash_is_not_silently_normalized_and_nan_is_rejected(self):
        opt = optimizer()
        for value in [current()*0.98,current().mask(current().index=="A0")]:
            with self.assertRaises(ValueError):
                opt.risk_tolerant(value)

    def test_solver_failure_retries_then_raises_never_keep(self):
        opt = optimizer()
        with patch.object(cp.Problem,"solve",side_effect=cp.error.SolverError("synthetic failure")):
            with self.assertRaises(OptimizationError) as caught:
                opt.risk_tolerant(current())
        self.assertEqual(len(caught.exception.attempts),2)
        self.assertTrue(all(not x["accepted"] for x in caught.exception.attempts))

    def test_inaccurate_status_is_not_silently_accepted(self):
        def inaccurate(problem,*args,**kwargs):
            problem._status = cp.OPTIMAL_INACCURATE
            problem._solver_stats = type("Stats",(),{"num_iters":1})()
        with patch.object(cp.Problem,"solve",inaccurate):
            with self.assertRaises(OptimizationError):
                optimizer().minimum_variance()

    def test_optimal_status_does_not_override_invalid_weights(self):
        original_solve = cp.Problem.solve
        def corrupted(problem,*args,**kwargs):
            original_solve(problem,*args,**kwargs)
            variable = problem.variables()[0]
            variable.value = variable.value+.01
        with patch.object(cp.Problem,"solve",corrupted):
            with self.assertRaises(OptimizationError) as caught:
                optimizer().minimum_variance()
        self.assertTrue(all("budget/position" in a["error"] for a in caught.exception.attempts))


if __name__ == "__main__":
    unittest.main()
