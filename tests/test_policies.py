"""Calendar boundaries and the connection between holdings and optimization."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import project_runtime  # noqa: F401
import numpy as np
import pandas as pd
from risk_rebalancing.ledger import CloseContext, HoldingsEngine, MarketTape
from risk_rebalancing.policies import PortfolioPolicy, calendar_due


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(7029)
        cls.dates = pd.bdate_range("2018-01-01",periods=310)
        cls.names = tuple("ABCDEFGHI")
        cls.returns = pd.DataFrame(rng.normal(0,np.linspace(.005,.04,9),(310,9)),index=cls.dates,columns=cls.names)

    def context(self, weights=None, index=280):
        weights = tuple(np.ones(9)/9) if weights is None else tuple(weights)
        return CloseContext(self.dates[index],self.dates[index+1],self.names,weights,100,0,0,0,self.returns.iloc[:index+1].copy())

    def test_holiday_week_end_and_month_end_use_calendar(self):
        self.assertTrue(calendar_due(pd.Timestamp("2020-04-09"),pd.Timestamp("2020-04-13"),"weekly"))
        self.assertTrue(calendar_due(pd.Timestamp("2020-07-31"),pd.Timestamp("2020-08-03"),"monthly"))
        self.assertFalse(calendar_due(pd.Timestamp("2020-07-30"),pd.Timestamp("2020-07-31"),"monthly"))
        self.assertFalse(calendar_due(pd.Timestamp("2020-07-29"),pd.Timestamp("2020-07-30"),"weekly"))

    def test_calendar_keep_does_not_reset_drifted_weights(self):
        context = self.context([.2]+[.1]*8)
        self.assertFalse(calendar_due(context.date,context.next_session,"monthly"))
        result = PortfolioPolicy(kind="minimum_variance",frequency="monthly")(context)
        self.assertEqual(result.action,"KEEP")
        self.assertIsNone(result.target_weights)

    def test_off_schedule_cap_repair(self):
        context = self.context([.3]+[.0875]*8)
        result = PortfolioPolicy(kind="minimum_variance",frequency="monthly")(context)
        self.assertEqual(result.reason,"cap_repair")
        self.assertEqual(result.action,"TARGET")
        self.assertLessEqual(max(result.target_weights),.25+1e-8)

    def test_equal_weight_monthly_reference_and_cap_monitoring(self):
        index = next(i for i in range(252,309) if calendar_due(self.dates[i],self.dates[i+1],"monthly"))
        result = PortfolioPolicy(kind="equal_weight",frequency="monthly")(self.context(index=index))
        np.testing.assert_allclose(result.target_weights,np.ones(9)/9)
        repair = PortfolioPolicy(kind="equal_weight",frequency="monthly")(self.context([.3]+[.0875]*8))
        self.assertEqual(repair.reason,"cap_repair")

    def test_all_daily_model_policies_emit_dated_diagnostics(self):
        for kind in ("risk_tolerant","minimum_variance","weight_band","variance_penalty"):
            with self.subTest(kind=kind):
                context = self.context()
                result = PortfolioPolicy(kind=kind)(context)
                self.assertIn(result.action,("KEEP","TARGET"))
                self.assertEqual(result.diagnostics["window_end"],context.date.isoformat())
                self.assertEqual(np.asarray(result.covariance).shape,(9,9))

    def test_missing_selected_risk_observation_propagates_failure(self):
        context = self.context()
        context.risk_returns.iloc[-1,0] = np.nan
        with self.assertRaisesRegex(ValueError,"missing"):
            PortfolioPolicy()(context)

    def test_policy_engine_cap_mismatch_rejected(self):
        prices = pd.DataFrame(100.,index=self.dates[280:282],columns=self.names)
        tape = MarketTape(self.names,prices,prices,self.returns,self.dates)
        with self.assertRaisesRegex(ValueError,"caps must agree"):
            HoldingsEngine(tape,cap=.3).run(PortfolioPolicy(cap=.25))

    def test_future_risk_and_prices_cannot_change_past_model_decisions(self):
        dates = self.dates[280:284]
        prices = pd.DataFrame(100*np.cumprod(1+self.returns.loc[dates].to_numpy(),axis=0),index=dates,columns=self.names)
        tape = MarketTape(self.names,prices,prices,self.returns,self.dates)
        changed = prices.copy()
        changed.iloc[-1] *= np.linspace(.5,2,9)
        changed_returns = self.returns.copy()
        changed_returns.loc[dates[-1]:] *= -2
        altered = MarketTape(self.names,changed,changed,changed_returns,self.dates)
        first = HoldingsEngine(tape).run(PortfolioPolicy())
        second = HoldingsEngine(altered).run(PortfolioPolicy())
        pd.testing.assert_frame_equal(first.daily.iloc[:-1],second.daily.iloc[:-1])
        self.assertEqual(first.trades[:-1],second.trades[:-1])
        # Full nested solver diagnostics can contain run-time fields; compare economic outputs.
        for a,b in zip(first.signals[:-1],second.signals[:-1]):
            self.assertEqual(a["action"],b["action"])
            self.assertEqual(a["target_weights"],b["target_weights"])


if __name__ == "__main__":
    unittest.main()
