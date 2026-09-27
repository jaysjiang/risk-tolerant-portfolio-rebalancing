"""Artificial demonstration market; never empirical evidence."""
import numpy as np
import pandas as pd
from risk_rebalancing.ledger import CorporateAction, MarketTape
SEED = 20260926

def synthetic_tape(size, seed=SEED):
    """A nominal tape with dividends, a parent/child event and a genuine split."""
    rng = np.random.default_rng(seed+size)
    calendar = pd.bdate_range("2018-01-01",periods=340)
    names = tuple(f"SYNTHETIC_{i+1}" for i in range(size))
    columns = list(names)+["SYNTHETIC_CHILD"]
    start, stop = 280, 316  # enough sessions to exercise weekly and month-end rules
    op = pd.DataFrame(index=calendar[:stop],columns=columns,dtype=float)
    cl = op.copy()
    returns = pd.DataFrame(index=calendar[:stop],columns=names,dtype=float)
    actions = (
        CorporateAction("synthetic_cash","cash",names[0],calendar[284],1.2,calendar[287]),
        CorporateAction("synthetic_child","in_kind",names[1],calendar[290],.1,calendar[293],columns[-1]),
        CorporateAction("synthetic_split","split",names[2],calendar[301],2.),
        CorporateAction("synthetic_terminal_cash","cash",names[-1],calendar[314],.8,calendar[322]),
    )
    previous = np.full(size+1,100.)
    for i,date in enumerate(calendar[:stop]):
        factor = rng.normal(0,.007)
        overnight = .25*factor + rng.normal(0,np.linspace(.002,.006,size+1))
        intraday = .75*factor + rng.normal(0,np.linspace(.003,.013,size+1))
        split = np.ones(size+1)
        cash = np.zeros(size+1)
        child_units = np.zeros(size+1)
        for a in actions:
            if date != a.ex_date:
                continue
            k = columns.index(a.ticker)
            if a.kind == "split": split[k] = a.amount
            elif a.kind == "cash": cash[k] = a.amount
            else: child_units[k] = a.amount
        open_values = previous/split*(1+overnight)
        open_values -= cash+child_units*open_values[-1]
        close_values = open_values*(1+intraday)
        op.loc[date],cl.loc[date] = open_values,close_values
        returns.loc[date] = (split*(close_values+cash+child_units*close_values[-1])/previous-1)[:size]
        previous = close_values
    return MarketTape(names,op.iloc[start:],cl.iloc[start:],returns,calendar,actions)
