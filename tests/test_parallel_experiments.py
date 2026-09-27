"""Process scheduling must preserve every financial output and useful failures."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project_runtime  # noqa: F401
import numpy as np
from public_io import read_json
from synthetic_data import synthetic_tape
from risk_rebalancing.experiments import run_grid, policy_grid, ParallelPolicyError


class ParallelExperimentsTests(unittest.TestCase):
    def test_serial_and_process_artifacts_are_identical(self):
        with tempfile.TemporaryDirectory(prefix="parallel-test-") as folder:
            tape = synthetic_tape(9)
            grid = policy_grid()
            configs = [grid[0], grid[4], grid[-2]]
            serial, parallel = Path(folder)/"serial", Path(folder)/"parallel"
            a = run_grid(tape, serial, scope="synthetic", provenance={}, configurations=configs)
            b = run_grid(tape, parallel, scope="synthetic", provenance={}, configurations=configs, max_workers=2)
            self.assertEqual(a, b)
            ma, mb = read_json(serial/"manifest.json"), read_json(parallel/"manifest.json")
            self.assertEqual(ma["artifacts_sha256"], mb["artifacts_sha256"])
            self.assertEqual(mb["completed_configurations"], [name for name, _ in configs])
            self.assertEqual(mb["status"], "COMPLETED")
            self.assertEqual(mb["max_workers"], 2)

    def test_worker_failure_retains_decision_date_and_traceback(self):
        with tempfile.TemporaryDirectory(prefix="parallel-failure-") as folder:
            tape = synthetic_tape(9)
            returns = tape.risk_returns.copy()
            returns.loc[tape.opens.index[0], tape.tickers[0]] = np.nan
            tape = replace(tape, risk_returns=returns)
            output = Path(folder)/"failed"
            with self.assertRaises(ParallelPolicyError):
                run_grid(tape, output, scope="synthetic", provenance={}, configurations=policy_grid()[:2], max_workers=2)
            manifest, failure = read_json(output/"manifest.json"), read_json(output/"failure_context.json")
            self.assertEqual(manifest["status"], "FAILED")
            self.assertEqual(failure["error_type"], "ValueError")
            self.assertEqual(failure["decision"]["date"], str(tape.opens.index[0].date()))
            self.assertIn("selected return window", failure["traceback"])
            self.assertFalse((output/"metrics.json").exists())


if __name__ == "__main__": unittest.main()
