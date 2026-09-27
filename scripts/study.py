"""Frozen final scenarios; no selection on the evaluation period."""
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
from public_io import read_json, check_hashes
from risk_rebalancing.experiments import policy_grid
from risk_rebalancing.ledger import MarketTape, CorporateAction
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = read_json(ROOT / "reports/results/replay_contract.json")
SCENARIOS = tuple(CONTRACT["scenarios"])

def scenario_grid(scenario):
    if scenario not in SCENARIOS:
        raise ValueError("Not a prespecified final scenario")
    return [(n, replace(p, window=scenario["window"], estimator=scenario["estimator"])) for n, p in policy_grid()]


def paired_records(folder, a, b):
    da, db = (pd.read_parquet(Path(folder) / n / "daily.parquet") for n in (a, b))
    if not da.index.equals(db.index) or da.index.has_duplicates or not da.index.is_monotonic_increasing:
        raise ValueError("Policies have unaligned daily records")
    values = np.column_stack([da.gross_return, db.gross_return, da.routine_turnover, db.routine_turnover])
    return values, da.index

def load_reviewed_tape(folder):
    folder = Path(folder)
    missing = [name for name in CONTRACT['input_sha256'] if not (folder/name).is_file()]
    if missing:
        raise ValueError('Reviewed input files are not distributed. Supply --data-dir with all five original snapshots; see docs/data_availability.md. Missing: ' + ', '.join(missing))
    check_hashes(folder, CONTRACT['input_sha256'])
    check_hashes(ROOT, CONTRACT['core_sha256'])
    tape = MarketTape(tuple(CONTRACT['tickers']), pd.read_parquet(folder/'input_opens.parquet'),
                      pd.read_parquet(folder/'input_closes.parquet'), pd.read_parquet(folder/'input_risk_returns.parquet'),
                      pd.DatetimeIndex(read_json(folder/'input_calendar.json')),
                      tuple(CorporateAction(**a) for a in read_json(folder/'input_actions.json')))
    if len(tape.opens) != CONTRACT['sessions'] or str(tape.opens.index[0].date()) != CONTRACT['start'] or str(tape.opens.index[-1].date()) != CONTRACT['end']:
        raise ValueError('Reviewed tape dates differ from frozen evaluation')
    return tape
