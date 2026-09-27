"""Hand-calculated ledger examples, event ordering and information barriers."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import project_runtime  # noqa: F401
import numpy as np
import pandas as pd
from risk_rebalancing.ledger import (CorporateAction, MarketTape, Instruction,
                                    HoldingsEngine, fund_target)


def keep(context):
    return Instruction("KEEP")


def tape(opens, closes=None, actions=(), names=("A","B"), columns=None):
    op = np.asarray(opens,dtype=float)
    dates = pd.bdate_range("2020-01-06",periods=len(op)+3)
    columns = list(names) if columns is None else columns
    opening = pd.DataFrame(op,index=dates[:len(op)],columns=columns)
    closing = pd.DataFrame(op if closes is None else closes,index=opening.index,columns=columns)
    returns = pd.DataFrame(0.,index=opening.index,columns=names)
    return MarketTape(names,opening,closing,returns,dates,tuple(actions))


def run(market, policy=keep, cost=0., lag=1, **kwargs):
    return HoldingsEngine(market,cost_rate=cost,cap=1.,execution_lag=lag).run(policy,initial_capital=100.,**kwargs)


class FundedSizingTests(unittest.TestCase):
    def test_entry_exact_cost_funding(self):
        result = fund_target([0,0],100,[.5,.5],.01)
        self.assertAlmostEqual(result.post_etf_wealth,100/1.01,places=12)
        self.assertAlmostEqual(result.cost,100/101,places=12)
        self.assertAlmostEqual(sum(result.post_values)+result.cash+result.cost,100)

    def test_full_switch_costs_both_sides(self):
        result = fund_target([100,0],0,[0,1],.01)
        self.assertAlmostEqual(result.post_etf_wealth,100*.99/1.01)
        self.assertAlmostEqual(result.traded_notional,100+result.post_etf_wealth)
        self.assertGreaterEqual(result.cash,0)

    def test_zero_cost_and_unchanged_target(self):
        self.assertEqual(fund_target([70,30],0,[.7,.3],0).post_values,(70.,30.))
        result = fund_target([70,30],0,[.7,.3],.01)
        self.assertLess(result.traded_notional,1e-12)

    def test_invalid_or_unfunded_inputs_rejected(self):
        cases = [([1,-1],0,[.5,.5],.01),([1,1],-1,[.5,.5],.01),
                 ([1,1],0,[.5,.6],.01),([1,1],0,[.5,.5],1),
                 ([1,1],0,[np.nan,.5],.01)]
        for args in cases:
            with self.subTest(args=args),self.assertRaises(ValueError):
                fund_target(*args)


class TimingTests(unittest.TestCase):
    def test_keep_retains_shares_not_target_weights(self):
        result = run(tape([[10,10],[20,10],[20,20]]))
        self.assertEqual(result.final_shares,{"A":5.,"B":5.})
        self.assertAlmostEqual(result.daily.iloc[1].weight_A,2/3)
        self.assertEqual(len(result.trades),1)

    def test_overnight_old_holdings_then_frozen_target(self):
        market = tape([[10,10],[20,10]],[[10,10],[40,10]])
        policy = lambda c: Instruction("TARGET",(0.,1.))
        result = run(market,policy)
        self.assertEqual(result.daily.iloc[0].nav,100)
        self.assertEqual(result.daily.iloc[1].nav,150)  # A's overnight gain, no later A gain
        self.assertEqual(result.final_shares,{"A":0.,"B":15.})
        trade = result.trades[1]
        self.assertEqual(trade["signal_date"],market.opens.index[0].isoformat())
        self.assertEqual(trade["date"],market.opens.index[1].isoformat())
        self.assertEqual(trade["target_weights"],[0.,1.])

    def test_no_same_close_trade_and_end_target_unfilled(self):
        market = tape([[10,10]],[[20,10]])
        result = run(market,lambda c: Instruction("TARGET",(0.,1.)))
        self.assertEqual(result.final_shares,{"A":5.,"B":5.})
        self.assertEqual(result.daily.iloc[0].nav,150)
        self.assertEqual(result.signals[0]["status"],"unfilled_at_end")

    def test_two_session_fifo_keep_does_not_cancel_older_target(self):
        market = tape([[10,10]]*4)
        policy = lambda c: Instruction("TARGET",(1.,0.)) if c.date==market.opens.index[0] else Instruction("KEEP")
        result = run(market,policy,lag=2)
        self.assertEqual(result.daily.iloc[1].shares_A,5)
        self.assertEqual(result.daily.iloc[2].shares_A,10)
        self.assertEqual(result.daily.iloc[3].shares_A,10)
        self.assertEqual(result.trades[1]["date"],market.opens.index[2].isoformat())

    def test_policy_sees_only_completed_returns_and_can_not_mutate_tape(self):
        market = tape([[10,10]]*3)
        def inspect(context):
            self.assertEqual(context.risk_returns.index[-1],context.date)
            context.risk_returns.iloc[:,:] = 99
            return Instruction("KEEP")
        run(market,inspect)
        self.assertTrue((market.risk_returns==0).all().all())

    def test_fresh_blocks_reset_and_initial_entry_excludes_routine_turnover(self):
        market = tape([[10,10],[20,10],[30,10]])
        result = run(market,start=market.opens.index[1])
        self.assertEqual(result.trades[0]["pre_shares"],{"A":0.,"B":0.})
        self.assertEqual(result.daily.iloc[0].nav,100)
        self.assertEqual(result.daily.routine_turnover.sum(),0)

    def test_invalid_target_and_solver_exception_do_not_become_keep(self):
        market = tape([[10,10]])
        for inst in (Instruction("KEEP",(.5,.5)),Instruction("TARGET",(.8,.8)),Instruction("SILENT_FALLBACK")):
            with self.assertRaises(ValueError):
                run(market,lambda c:inst)
        def fail(context):
            raise RuntimeError("solver failure")
        with self.assertRaisesRegex(RuntimeError,"solver failure"):
            run(market,fail)


class CorporateActionTests(unittest.TestCase):
    def test_cash_dividend_accrual_paydate_and_prorata_reinvestment(self):
        action = CorporateAction("div","cash","A","2020-01-07",2,"2020-01-08")
        result = run(tape([[10,10],[8,10],[8,10],[8,10]],actions=[action]))
        self.assertEqual(result.daily.iloc[1].cash_receivable,10)
        self.assertEqual(result.daily.iloc[1].settled_cash,0)
        self.assertEqual(result.daily.iloc[2].cash_receivable,0)
        self.assertEqual(result.daily.iloc[2].settled_cash,10)
        self.assertTrue(np.allclose(result.daily.nav,100))
        self.assertAlmostEqual(result.daily.iloc[3].weight_A,4/9)
        self.assertEqual([t["reason"] for t in result.trades],["initial_entry","cash_reinvestment"])
        self.assertAlmostEqual(result.trades[-1]["traded_notional"],10)

    def test_exdate_buyer_not_entitled_and_prior_owner_keeps_receivable_after_sale(self):
        action = CorporateAction("div","cash","A","2020-01-07",2,"2020-01-09")
        market = tape([[10,10],[8,10],[8,10],[8,10]],actions=[action])
        fresh = run(market,start=market.opens.index[1])
        self.assertEqual(fresh.daily.cash_receivable.sum(),0)
        sold = run(market,lambda c:Instruction("TARGET",(0.,1.)))
        self.assertEqual(sold.daily.iloc[1].shares_A,0)
        self.assertEqual(sold.daily.iloc[1].cash_receivable,10)
        self.assertEqual(sold.daily.iloc[-1].settled_cash,10)

    def test_nontrading_payment_released_at_next_session_close(self):
        market = tape([[10,10]]*7)
        action = CorporateAction("div","cash","A","2020-01-07",1,"2020-01-11")
        market = MarketTape(market.tickers,market.opens,market.closes,market.risk_returns,market.calendar,(action,))
        result = run(market)
        self.assertEqual(result.daily.loc["2020-01-10"].cash_receivable,5)
        self.assertEqual(result.daily.loc["2020-01-13"].settled_cash,5)
        self.assertEqual(result.trades[-1]["date"],pd.Timestamp("2020-01-14").isoformat())

    def test_split_is_wealth_neutral_and_changes_share_units(self):
        split = CorporateAction("split","split","A","2020-01-07",2)
        result = run(tape([[10,10],[5,10]],actions=[split]))
        self.assertEqual(result.final_shares,{"A":10.,"B":5.})
        self.assertEqual(result.daily.iloc[-1].nav,100)
        self.assertEqual(len(result.trades),1)

    def test_same_day_split_precedes_postsplit_cash_entitlement(self):
        actions = [CorporateAction("d","cash","A","2020-01-07",1,"2020-01-09"),
                   CorporateAction("s","split","A","2020-01-07",2)]
        result = run(tape([[10,10],[4,10]],actions=actions))
        self.assertEqual(result.daily.iloc[-1].cash_receivable,10)
        self.assertEqual(result.daily.iloc[-1].nav,100)

    def test_in_kind_is_marked_pending_delivered_then_sold(self):
        action = CorporateAction("child","in_kind","A","2020-01-07",.5,"2020-01-08","C")
        market = tape([[10,10,2],[9,10,2],[9,10,4],[9,10,4]],actions=[action],columns=["A","B","C"])
        result = run(market)
        self.assertEqual(result.daily.iloc[1].child_receivable,5)
        self.assertEqual(result.daily.iloc[1].nav,100)
        self.assertEqual(result.daily.iloc[2].settled_auxiliary,10)
        self.assertEqual(result.daily.iloc[2].nav,105)
        self.assertEqual(result.daily.iloc[2].shares_A,5)
        self.assertEqual([t["reason"] for t in result.trades],["initial_entry","auxiliary_sale","cash_reinvestment"])
        self.assertEqual(result.final_shares["C"],0)
        self.assertAlmostEqual(result.daily.iloc[-1].nav,105)

    def test_split_adjusts_pending_child_units(self):
        actions = [CorporateAction("child","in_kind","A","2020-01-07",.5,"2020-01-10","C"),
                   CorporateAction("split_child","split","C","2020-01-08",2)]
        market = tape([[10,10,2],[9,10,2],[9,10,1]],actions=actions,columns=["A","B","C"])
        result = run(market)
        self.assertEqual(result.outstanding_receivables[0]["amount"],5)
        self.assertEqual(result.daily.iloc[-1].child_receivable,5)
        self.assertEqual(result.daily.iloc[-1].nav,100)

    def test_pending_child_distribution_requires_review(self):
        actions = [CorporateAction("child","in_kind","A","2020-01-07",.5,"2020-01-10","C"),
                   CorporateAction("childdiv","cash","C","2020-01-08",1,"2020-01-10")]
        with self.assertRaisesRegex(ValueError,"beneficial-rights"):
            run(tape([[10,10,2]]*3,actions=actions,columns=["A","B","C"]))

    def test_missing_held_child_price_raises_but_unheld_missing_is_allowed(self):
        action = CorporateAction("child","in_kind","A","2020-01-07",.5,"2020-01-08","C")
        run(tape([[10,10,np.nan]]*2,columns=["A","B","C"]))
        with self.assertRaisesRegex(ValueError,"Missing required quote"):
            run(tape([[10,10,np.nan]]*2,actions=[action],columns=["A","B","C"]))

    def test_paydate_cash_combined_with_target_without_duplicate_reinvestment(self):
        action = CorporateAction("div","cash","A","2020-01-07",2,"2020-01-07")
        market = tape([[10,10],[8,10],[8,10]],actions=[action])
        def policy(context):
            return Instruction("TARGET",(.5,.5)) if context.date==market.opens.index[1] else Instruction("KEEP")
        result = run(market,policy,cost=.001)
        self.assertEqual([t["reason"] for t in result.trades],["initial_entry","policy"])
        self.assertGreater(result.trades[-1]["settled_cash_deployed"],9)
        self.assertAlmostEqual(result.daily.iloc[-1].weight_A,.5)

    def test_terminal_receivables_not_discarded_or_liquidated(self):
        action = CorporateAction("div","cash","A","2020-01-07",2,"2020-02-01")
        result = run(tape([[10,10],[8,10]],actions=[action]))
        self.assertEqual(result.daily.iloc[-1].nav,100)
        self.assertEqual(len(result.outstanding_receivables),1)
        self.assertEqual(len(result.trades),1)


class ReturnAndInputTests(unittest.TestCase):
    def test_entry_cost_removed_gross_return_keeps_open_to_close_exposure(self):
        result = run(tape([[10,10]],[[12,10]]),cost=.01)
        self.assertAlmostEqual(result.daily.iloc[0].gross_return,.1)
        self.assertAlmostEqual(result.daily.iloc[0].net_return,1.1/1.01-1)
        self.assertEqual(result.daily.iloc[0].routine_turnover,0)

    def test_multiple_cost_events_product_removal_and_cash_funding(self):
        action = CorporateAction("child","in_kind","A","2020-01-07",.5,"2020-01-07","C")
        market = tape([[10,10,2],[9,10,2],[9,10,2]],
                      [[10,10,2],[9,10,2],[18,10,2]],actions=[action],columns=["A","B","C"])
        result = run(market,cost=.01)
        row = result.daily.iloc[-1]
        events = [t for t in result.trades if t["date"]==row.name.isoformat()]
        self.assertEqual(len(events),2)
        expected = (1+row.net_return)*np.prod([t["pre_nav"]/t["post_nav"] for t in events])-1
        self.assertAlmostEqual(row.gross_return,expected)
        self.assertNotAlmostEqual(row.gross_return,row.net_return+row.total_cost/result.daily.iloc[-2].nav,places=6)
        for trade in result.trades:
            self.assertAlmostEqual(trade["pre_nav"]-trade["post_nav"],trade["cost"])
            self.assertGreaterEqual(trade["post_cash"],0)
        self.assertTrue(np.allclose(run(market).daily.gross_return,run(market).daily.net_return))

    def test_future_perturbation_leaves_earlier_ledger_unchanged(self):
        market = tape([[10,10],[11,9],[12,8],[13,7]])
        changed_open,changed_close,changed_returns = market.opens.copy(),market.closes.copy(),market.risk_returns.copy()
        changed_open.iloc[3] *= [2,3]
        changed_close.iloc[3] *= [4,5]
        changed_returns.iloc[3] = [.9,-.8]
        other = MarketTape(market.tickers,changed_open,changed_close,changed_returns,market.calendar)
        policy = lambda c:Instruction("TARGET",(.4,.6))
        first,second = run(market,policy,cost=.001),run(other,policy,cost=.001)
        pd.testing.assert_frame_equal(first.daily.iloc[:3],second.daily.iloc[:3])
        self.assertEqual(first.trades[:3],second.trades[:3])
        self.assertEqual(first.signals[:3],second.signals[:3])

    def test_invalid_action_inputs_and_duplicate_economic_event(self):
        with self.assertRaises(ValueError):
            CorporateAction("bad","cash","A","2020-01-07",1,"2020-01-06")
        a = CorporateAction("a","cash","A","2020-01-07",1,"2020-01-08")
        b = CorporateAction("b","cash","A","2020-01-07",1,"2020-01-08")
        with self.assertRaisesRegex(ValueError,"Duplicate economic"):
            tape([[10,10]]*3,actions=[a,b])

    def test_adjusted_prices_missing_sessions_and_short_calendar_rejected(self):
        market = tape([[10,10]]*3)
        with self.assertRaisesRegex(ValueError,"nominal_unadjusted"):
            MarketTape(market.tickers,market.opens,market.closes,market.risk_returns,market.calendar,price_basis="adjusted")
        with self.assertRaisesRegex(ValueError,"Missing trading session"):
            MarketTape(market.tickers,market.opens.iloc[[0,2]],market.closes.iloc[[0,2]],market.risk_returns,market.calendar)
        short = MarketTape(market.tickers,market.opens,market.closes,market.risk_returns,market.opens.index)
        with self.assertRaisesRegex(ValueError,"future buffer"):
            run(short)

    def test_missing_return_session_cannot_lengthen_effective_risk_window(self):
        market = tape([[10,10]]*3)
        with self.assertRaisesRegex(ValueError,"skipped trading sessions"):
            MarketTape(market.tickers,market.opens,market.closes,market.risk_returns.iloc[[0,2]],market.calendar)

    def test_frozen_instruction_does_not_share_mutable_target_list(self):
        weights = [.5,.5]
        inst = Instruction("TARGET",weights)
        weights[:] = [0.,1.]
        self.assertEqual(inst.target_weights,(.5,.5))



if __name__ == "__main__":
    unittest.main()
