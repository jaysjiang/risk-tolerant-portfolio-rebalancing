from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import project_runtime  # noqa: F401
import numpy as np
from risk_rebalancing.mechanisms import (turnover_decomposition, variance_contributions,
    exposure_projection, largest_share, trigger_category, empirical_dominators)


class MechanismAccountingTests(unittest.TestCase):
    def test_frequency_and_size_reconcile_including_tiny_positive_trades(self):
        q=np.array([0.,.1,0.,.3,1e-15])
        r=turnover_decomposition(q)
        self.assertEqual(r['active_days'],3)
        self.assertAlmostEqual(r['annual_turnover'],252*q.mean())

    def test_zero_turnover_is_defined_without_active_days(self):
        r=turnover_decomposition([0,0,0])
        self.assertEqual(r['mean_turnover_active_day'],0.)
        self.assertIsNone(largest_share([0,0],1))

    def test_invalid_or_negative_inputs_do_not_get_dropped(self):
        for values in ([0,float('nan')],[0,-.01],[]):
            with self.assertRaises(ValueError):turnover_decomposition(values)

    def test_variance_attribution_uses_global_means_and_denominator(self):
        a=np.array([.1,-.1,.03,-.02]); b=np.array([.02,-.01,.01,.02])
        r=variance_contributions(a,b,[2020,2020,2021,2021])
        manual=252*sum((a[:2]-a.mean())**2-(b[:2]-b.mean())**2)/3
        self.assertAlmostEqual(r['periods'][0]['annual_variance_difference_contribution'],manual)
        self.assertAlmostEqual(sum(x['annual_variance_difference_contribution'] for x in r['periods']),252*(a.var(ddof=1)-b.var(ddof=1)))

    def test_exposure_projection_exact_affine_relation(self):
        x=np.array([-.02,.03,.01,-.01,.02]); y=.001+1.7*x
        r=exposure_projection(y,x)
        self.assertAlmostEqual(r['beta_to_monthly_equal_weight'],1.7)
        self.assertAlmostEqual(r['intercept_daily_descriptive_only'],.001)
        self.assertLess(r['residual_annual_variance'],1e-25)

    def test_exposure_projection_with_orthogonal_residual(self):
        x=np.array([-1.,0.,1.]); y=np.array([1.,-2.,1.])*.01+x*.02
        r=exposure_projection(y,x)
        self.assertAlmostEqual(r['beta_to_monthly_equal_weight'],.02)
        self.assertAlmostEqual(r['reference_component_annual_variance']+r['residual_annual_variance'],252*y.var(ddof=1))
        with self.assertRaises(ValueError):exposure_projection(y,[1,1,1])

    def test_top_share_and_cap_risk_categories(self):
        self.assertAlmostEqual(largest_share([1,3,0,6],2),.9)
        for cap,risk,label in [(False,1.,'neither'),(True,1.,'cap_only'),(False,1.1,'risk_only'),(True,1.1,'both')]:
            s={'diagnostics':{'cap_breached_at_close':cap,'current_sleeve_forecast_variance':risk,'reference_variance_daily':1.}}
            self.assertEqual(trigger_category(s),label)

    def test_dominance_requires_both_dimensions_and_one_strict(self):
        def row(name,v,t):return {'id':name,'annualized_gross_volatility':v,'annualized_full_notional_turnover':t}
        rows=[row('A',.2,1),row('same',.2,1),row('lower_risk',.1,2),row('better',.19,.9)]
        self.assertEqual(empirical_dominators(rows,'A'),['better'])


if __name__=='__main__':unittest.main()
