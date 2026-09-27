"""Public checks and synthetic demo; financial replay needs reviewed private inputs."""
import argparse
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote
import uuid

for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(key, '1')
sys.dont_write_bytecode = True
import project_runtime  # noqa: E402,F401
import numpy as np
from public_io import check_hashes, compare_metrics, read_json
from risk_rebalancing.experiments import policy_grid, run_grid, write_json
from risk_rebalancing.inference import paired_bootstrap
from risk_rebalancing.ledger import MarketTape
from study import CONTRACT, SCENARIOS, load_reviewed_tape, paired_records, scenario_grid
from synthetic_data import synthetic_tape

ROOT = Path(__file__).resolve().parents[1]


def check_links():
    count = 0
    for document in ROOT.rglob('*.md'):
        if 'work' in document.relative_to(ROOT).parts:
            continue
        for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            target = unquote(target.split('#', 1)[0]).strip('<>')
            if not target or re.match(r'^[a-zA-Z]+:', target):
                continue
            file = (document.parent / target).resolve()
            if not file.is_relative_to(ROOT) or not file.exists():
                raise ValueError(f'Broken local link in {document.relative_to(ROOT)}: {target}')
            # Check spelling on Windows too: GitHub's Linux filesystem is case sensitive.
            current = ROOT
            for part in file.relative_to(ROOT).parts:
                if part not in {p.name for p in current.iterdir()}:
                    raise ValueError(f'Case mismatch: {target}')
                current /= part
            count += 1
    return count


def check_release():
    manifest = read_json(ROOT / 'release_manifest.json')
    check_hashes(ROOT, manifest['files_sha256'])
    check_hashes(ROOT, CONTRACT['core_sha256'])
    rows = read_json(ROOT / 'reports/results/all_policy_metrics.json')
    for scenario in SCENARIOS:
        subset = [r for r in rows if r['scenario'] == scenario['id']]
        if [r['id'] for r in subset] != [n for n, _ in policy_grid()]:
            raise ValueError('Incomplete or reordered frozen result grid')
        for row in subset:
            if row['sessions'] != 1508 or row['provisional']:
                raise ValueError('Invalid frozen result identity')
            np.testing.assert_allclose(row['annualized_routine_cost_debit_fraction'],
                                       scenario['cost_bps']/10000 * row['annualized_full_notional_turnover'],
                                       rtol=1e-12, atol=1e-12)
    if len(rows) != 189:
        raise ValueError('Expected 189 aggregate policy rows')
    freeze = read_json(ROOT / 'reports/results/frozen_selection.json')
    if datetime.fromisoformat(freeze['frozen_at_utc']) >= datetime.fromisoformat(freeze['final_started_at_utc']):
        raise ValueError('Selection does not precede final launch')
    return {'manifest_files': len(manifest['files_sha256']), 'local_links': check_links(),
            'aggregate_policy_rows': len(rows), 'financial_replay_performed': False}


def regression(out):
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out / 'tests.log').write_text(stream.getvalue(), encoding='utf-8')
    if not result.wasSuccessful():
        print(stream.getvalue(), file=sys.stderr)
        raise RuntimeError(f'Test failures: {out / "tests.log"}')
    print(f'PASS: {result.testsRun} public regression tests', flush=True)
    return result.testsRun


def replay(tape, out, mode, workers):
    a, b = CONTRACT['primary_A'], CONTRACT['primary_B']
    if mode == 'smoke':
        end = tape.opens.index[14]
        tape = MarketTape(tape.tickers, tape.opens.loc[:end], tape.closes.loc[:end],
                          tape.risk_returns.loc[:end], tape.calendar,
                          tuple(event for event in tape.actions if event.ex_date <= end))
    records = []
    expected = read_json(ROOT / 'reports/results/all_policy_metrics.json')
    inference = read_json(ROOT / 'reports/results/inference.json')
    for scenario in (SCENARIOS if mode == 'full' else SCENARIOS[:1]):
        configs = scenario_grid(scenario)
        if mode == 'smoke':
            configs = [(n, p) for n, p in configs if n in (a, b)]
        folder = out / 'runs' / scenario['id']
        rows = run_grid(tape, folder, scope='final_test',
                        provenance={'scenario': scenario, 'input_sha256': CONTRACT['input_sha256'],
                                    'replay_mode': mode}, configurations=configs,
                        cost_bps=scenario['cost_bps'], execution_lag=scenario['lag'], max_workers=workers,
                        progress=lambda name: print(f'Completed {name}', flush=True))
        record = {'scenario': scenario['id'], 'sessions': len(tape.opens), 'policies': len(rows)}
        if mode == 'full':
            reference = [{k:v for k,v in row.items() if k != 'scenario'}
                         for row in expected if row['scenario'] == scenario['id']]
            compare_metrics(rows, reference)
            values, _ = paired_records(folder, a, b)
            comparisons = []
            for block in ((20, 10, 60) if scenario['id'] == 'baseline' else (20,)):
                summary, _ = paired_bootstrap(values, mean_block=block)
                old = next(r for r in inference if r['scenario'] == scenario['id'] and r['mean_block'] == block)
                for key in ('classification', 'index_array_sha256'):
                    if summary[key] != old[key]:
                        raise ValueError(f'Bootstrap mismatch: {key}')
                for key in ('volatility_ratio', 'turnover_ratio'):
                    np.testing.assert_allclose(summary['intervals'][key]['percentile_95'],
                                               old['intervals'][key]['percentile_95'], rtol=1e-9, atol=1e-9)
                write_json(out / f'inference_{scenario["id"]}_L{block}.json', summary)
                comparisons.append(block)
            record.update(all_aggregate_metrics_match=True, bootstrap_blocks_checked=comparisons)
        else:
            record['scope'] = 'Input-verified 15-session execution check; no full-period performance claim.'
        records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='check', choices=['check','verify','tests','demo','smoke','full'])
    parser.add_argument('--workers', type=int, choices=range(1, 13), default=2)
    parser.add_argument('--data-dir', type=Path, help='External folder containing the five reviewed inputs')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'work', help='Parent for a new unique run folder')
    args = parser.parse_args()
    tape = None
    if args.mode in ('smoke', 'full'):
        if args.data_dir is None:
            parser.error('Financial replay requires --data-dir with the five reviewed snapshots; see docs/data_availability.md.')
        try:
            tape = load_reviewed_tape(args.data_dir)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    out = args.output_root / (args.mode + '_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    record = {'mode': args.mode, 'status': 'RUNNING'}
    try:
        record['release_checks'] = check_release()
        if args.mode in ('check', 'verify', 'tests'):
            record['tests_passed'] = regression(out)
        elif args.mode == 'demo':
            selected = {'equal_weight_monthly', 'minimum_variance_monthly', 'weight_band_0.08',
                        'variance_penalty_0.3', 'risk_tolerant_0.02'}
            rows = run_grid(synthetic_tape(9), out / 'synthetic', scope='synthetic',
                            provenance={'seed': 20260926, 'description': 'Artificial data; no empirical claims'},
                            configurations=[(n,p) for n,p in policy_grid() if n in selected], max_workers=args.workers)
            record.update(synthetic_only=True, policy_runs=len(rows), sessions_per_policy=36)
        else:
            record['replay'] = replay(tape, out, args.mode, args.workers)
        record['status'] = 'PASSED'
    except Exception as exc:
        record.update(status='FAILED', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        write_json(out / 'verification.json', record)
        print(f'Check record: {out / "verification.json"}', flush=True)


if __name__ == '__main__':
    main()
