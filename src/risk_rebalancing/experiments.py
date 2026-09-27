"""Prespecified experiment grid, metrics, and append-only run artifacts.

Financial entry points must first use the project's release guard. This module
also accepts synthetic tapes for offline verification of the full pipeline.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import importlib.metadata
import json
import multiprocessing
from pathlib import Path
import platform
import traceback

import numpy as np

from .ledger import HoldingsEngine
from .policies import PortfolioPolicy

BANDS = (.0025, .005, .01, .02, .04, .08)
PENALTIES = (.01, .03, .1, .3, 1., 3., 10.)
TOLERANCES = (0., .01, .02, .05)


def policy_grid():
    return [
        ("equal_weight_monthly", PortfolioPolicy(kind="equal_weight", frequency="monthly")),
        *[(f"minimum_variance_{f}", PortfolioPolicy(kind="minimum_variance", frequency=f))
          for f in ("daily", "weekly", "monthly")],
        *[(f"weight_band_{b:g}", PortfolioPolicy(kind="weight_band", band=b)) for b in BANDS],
        *[(f"variance_penalty_{p:g}", PortfolioPolicy(kind="variance_penalty", penalty=p)) for p in PENALTIES],
        *[(f"risk_tolerant_{e:g}", PortfolioPolicy(epsilon=e)) for e in TOLERANCES],
    ]


def metrics(result, initial_capital):
    daily = result.daily
    n = len(daily)
    if n < 2 or initial_capital <= 0:
        raise ValueError("Metrics require at least two sessions and positive initial capital")
    needed = ["nav", "gross_return", "net_return", "routine_turnover", "total_cost", "entry_cost",
              "routine_cost_debit_fraction", "discretionary_trade", "cash_fraction",
              "receivable_fraction", "auxiliary_fraction", "maximum_sleeve_weight"]
    if not np.isfinite(daily[needed].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite experiment output")
    if (daily.nav <= 0).any() or (daily.net_return <= -1).any():
        raise ValueError("Nonpositive portfolio wealth")
    terminal = float(daily.nav.iloc[-1])
    if not np.isclose(initial_capital * np.prod(1 + daily.net_return), terminal, rtol=1e-10, atol=1e-6):
        raise ValueError("Ledger NAV and compounded net returns do not reconcile")
    path = np.r_[initial_capital, daily.nav.to_numpy()]
    drawdown = path / np.maximum.accumulate(path) - 1
    signals = result.signals
    if len(signals) != n:
        raise ValueError("Expected exactly one after-close decision per session")
    if not set(s["action"] for s in signals).issubset({"KEEP", "TARGET"}):
        raise ValueError("Unknown decision action")
    return {
        "sessions": n, "terminal_nav_usd": terminal,
        "net_total_return": terminal / initial_capital - 1,
        "net_cagr_252_sessions": (terminal / initial_capital) ** (252 / n) - 1,
        "annualized_gross_volatility": float(daily.gross_return.std(ddof=1) * np.sqrt(252)),
        "annualized_net_volatility": float(daily.net_return.std(ddof=1) * np.sqrt(252)),
        "net_maximum_drawdown": float(drawdown.min()),
        "annualized_full_notional_turnover": float(daily.routine_turnover.sum() * 252 / n),
        "annualized_routine_cost_debit_fraction": float(daily.routine_cost_debit_fraction.sum() * 252 / n),
        "entry_cost_usd": float(daily.entry_cost.sum()),
        "routine_cost_usd": float(daily.total_cost.sum() - daily.entry_cost.sum()),
        "keep_decision_fraction": sum(s["action"] == "KEEP" for s in signals) / n,
        "no_discretionary_trade_fraction": float((~daily.discretionary_trade.astype(bool)).mean()),
        "cap_repair_decisions": sum(s["reason"] == "cap_repair" for s in signals),
        "unfilled_terminal_targets": sum(s["status"] == "unfilled_at_end" and s["action"] == "TARGET" for s in signals),
        "max_cash_fraction": float(daily.cash_fraction.max()),
        "max_receivable_fraction": float(daily.receivable_fraction.max()),
        "max_auxiliary_fraction": float(daily.auxiliary_fraction.max()),
        "max_close_sleeve_weight": float(daily.maximum_sleeve_weight.max()),
        "outstanding_receivables": len(result.outstanding_receivables),
    }


def json_value(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=json_value, allow_nan=False) + "\n", encoding="utf-8")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run_policy(tape, output, name, policy, scope, cost_bps, execution_lag, initial_capital):
    """One independent policy and its exclusive artifact folder; no shared writes."""
    result = HoldingsEngine(tape, cost_rate=cost_bps / 10000, cap=policy.cap,
                            execution_lag=execution_lag).run(policy, initial_capital=initial_capital)
    row = {"id": name, "provisional": scope == "provisional_development", **metrics(result, initial_capital)}
    folder = Path(output) / name
    folder.mkdir()
    result.daily.to_parquet(folder / "daily.parquet", index=True)
    for filename, records in (("trades", result.trades), ("decisions", result.signals), ("events", result.events)):
        with (folder / f"{filename}.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, default=json_value, allow_nan=False) + "\n")
    write_json(folder / "terminal.json", {
        "shares": result.final_shares, "cash": result.final_cash,
        "outstanding_receivables": result.outstanding_receivables,
    })
    write_json(folder / "metrics.json", row)
    return row


def _failure_value(value):
    """Keep failure details JSON/pickle safe, including failed numerical values."""
    if isinstance(value, np.ndarray):
        return _failure_value(value.tolist())
    if isinstance(value, np.generic):
        return _failure_value(value.item())
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else repr(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _failure_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_failure_value(item) for item in value]
    return repr(value)


def _failure_envelope(name, exc):
    return {"ok": False, "configuration": name,
            "error_type": type(exc).__name__, "error": f"{type(exc).__name__}: {exc}",
            "decision": _failure_value(getattr(exc, "decision_context", None)),
            "stage": _failure_value(getattr(exc, "stage", None)),
            "attempts": _failure_value(getattr(exc, "attempts", None)),
            "traceback": traceback.format_exc()}


def _policy_worker(tape, output, name, policy, scope, cost_bps, execution_lag, initial_capital):
    """Return data only: custom optimizer exceptions must never cross the pool."""
    try:
        row = _run_policy(tape, output, name, policy, scope, cost_bps, execution_lag, initial_capital)
        return {"ok": True, "configuration": name, "row": row}
    except Exception as exc:
        return _failure_envelope(name, exc)


class ParallelPolicyError(RuntimeError):
    """Parent-only exception reconstructed from a worker's plain-data failure."""
    def __init__(self, envelope):
        super().__init__(envelope["error"])
        self.envelope = envelope
        self.stage = envelope["stage"]
        self.attempts = envelope["attempts"]
        self.decision_context = envelope["decision"]


def _record_failure(out, manifest, envelope):
    manifest.update(status="FAILED", failed_configuration=envelope["configuration"],
                    error=envelope["error"])
    write_json(out / "failure_context.json", envelope)
    (out / "failure.txt").write_text(envelope["traceback"], encoding="utf-8")
    write_json(out / "manifest.json", manifest)


def run_grid(tape, output, *, scope, provenance, configurations=None, cost_bps=5., execution_lag=1,
             initial_capital=1_000_000., progress=None, max_workers=1):
    """Run independent policies; preserve grid order in all aggregate artifacts.

    The default stays in-process and preserves original exception types. Parallel
    callers must use a spawn-safe, importable entry point guarded by __main__.
    Progress callbacks run only in the parent, in completion order. On failure,
    mark FAILED immediately, cancel queued work, and drain running workers before
    hashing artifacts. No failed or partial grid is reported as a comparison.
    """
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
        raise ValueError("max_workers must be a positive integer")
    if scope not in {"development", "provisional_development", "validation", "final_test", "synthetic"}:
        raise ValueError("Unknown experiment scope")
    configs = list(policy_grid() if configurations is None else configurations)
    identifiers = [name for name, _ in configs]
    if not configs or len(set(identifiers)) != len(identifiers):
        raise ValueError("Configurations must be nonempty and uniquely named")
    if any(not name or Path(name).name != name or name in {".", ".."} for name in identifiers):
        raise ValueError("Unsafe configuration identifier")
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1, "status": "RUNNING", "scope": scope,
        "synthetic_only": scope == "synthetic", "provisional": scope == "provisional_development",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "start": str(tape.opens.index[0].date()), "end": str(tape.opens.index[-1].date()),
        "tickers": list(tape.tickers), "initial_capital_usd": initial_capital,
        "cost_bps_per_dollar_bought_or_sold": cost_bps, "execution_lag_sessions": execution_lag,
        "max_workers": max_workers,
        "configurations": [{"id": name, "settings": asdict(policy)} for name, policy in configs],
        "provenance": provenance, "python": platform.python_version(),
        "versions": {p: importlib.metadata.version(p) for p in
                     ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "cvxpy", "clarabel")},
        "completed_configurations": [], "selection_performed": False,
    }
    write_json(out / "manifest.json", manifest)
    rows = []
    completed = {}
    active = None

    def accept(name, row):
        completed[name] = row
        manifest["completed_configurations"] = [name for name in identifiers if name in completed]
        write_json(out / "manifest.json", manifest)
        if progress:
            progress(name)

    try:
        if max_workers == 1:
            for active, policy in configs:
                row = _run_policy(tape, out, active, policy, scope, cost_bps, execution_lag, initial_capital)
                accept(active, row)
        else:
            # Explicit spawn also avoids inheriting solver/thread state on POSIX.
            first_failure = None
            with ProcessPoolExecutor(max_workers=max_workers,
                                     mp_context=multiprocessing.get_context("spawn")) as pool:
                futures = {}
                try:
                    for active, policy in configs:
                        future = pool.submit(_policy_worker, tape, out, active, policy, scope,
                                             cost_bps, execution_lag, initial_capital)
                        futures[future] = active
                    for future in as_completed(futures):
                        if future.cancelled():
                            continue
                        active = futures[future]
                        try:
                            envelope = future.result()
                        except Exception as exc:
                            # Covers transport errors and abrupt worker exits too.
                            envelope = _failure_envelope(active, exc)
                        if envelope["ok"]:
                            accept(active, envelope["row"])
                        elif first_failure is None:
                            first_failure = envelope
                            _record_failure(out, manifest, envelope)
                            for pending in futures:
                                pending.cancel()
                    if first_failure is not None:
                        raise ParallelPolicyError(first_failure)
                except BaseException:
                    for pending in futures:
                        pending.cancel()
                    raise
            # Exiting the pool waits for all worker writes before final hashes.
        rows = [completed[name] for name in identifiers]
        write_json(out / "metrics.json", rows)
        title = "Synthetic pipeline verification — not financial evidence" if scope == "synthetic" else "Development sample — no validation or final-test selection"
        if scope == "provisional_development":
            title = "PROVISIONAL development sample — unresolved dividend assumptions; not final evidence"
        elif scope == "validation":
            title = "Validation sample — comparator selection inputs, not final-test evidence"
        elif scope == "final_test":
            title = "Final-test sample — frozen policy evaluation, no comparator reselection"
        lines = [f"# {title}", "", "All prespecified configurations are reported in their original order.", "",
                 "| Policy | Annual gross volatility | Annual full-notional turnover | KEEP decisions | Net max drawdown |",
                 "|---|---:|---:|---:|---:|"]
        lines += [f"| {r['id']} | {r['annualized_gross_volatility']:.2%} | {r['annualized_full_notional_turnover']:.3f} | {r['keep_decision_fraction']:.1%} | {r['net_maximum_drawdown']:.2%} |" for r in rows]
        lines += ["", "Turnover excludes initial entry; net NAV includes its cost. KEEP decisions can still coincide with mandatory cash reinvestment or child disposal. Gross returns remove actual cost debits on the same holdings path, not the returns of a separately rerun zero-cost policy."]
        (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        manifest["status"] = "COMPLETED"
    except Exception as exc:
        envelope = exc.envelope if isinstance(exc, ParallelPolicyError) else _failure_envelope(active, exc)
        _record_failure(out, manifest, envelope)
        raise
    finally:
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["artifacts_sha256"] = {
            p.relative_to(out).as_posix(): file_hash(p) for p in sorted(out.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        }
        write_json(out / "manifest.json", manifest)
    return rows
