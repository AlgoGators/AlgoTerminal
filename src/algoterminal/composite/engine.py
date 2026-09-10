"""Combine several already-backtested research records into one composite
book.

A composite doesn't fetch data or run any strategy code of its own -- it
only combines each leg's OWN already-saved backtest return stream, weighted
either equally or by inverse realized volatility (the latter equalizes each
leg's risk contribution, the same convention used ad hoc for the crack-
spread book this feature was built to generalize). That makes building or
rerunning a composite fast and side-effect-free: it never changes a leg's
own recorded numbers, and picks up a leg's latest saved backtest at combine
time -- rerun a leg's own backtest first if you want the composite to
reflect new numbers.

Leg return series are aligned on the union of their dates; a date only some
legs have data for treats the missing legs as flat (0 return) that day, not
as excluded from the sample -- simplest correct behavior when legs cover
different windows, but it understates the composite's risk over a stretch
where only one leg is actually trading. Legs on materially different-length
backtest windows should be rerun onto a common window first for a
meaningful combination.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import pandas as pd

from algoterminal.analytics.stats import PerformanceStats, drawdown_series, performance_stats
from algoterminal.composite.storage import CompositeRecord
from algoterminal.research.backtest import has_backtest_result, load_backtest_result
from algoterminal.research.storage import latest_record


class CompositeError(Exception):
    """A composite can't be built as requested (bad legs, no backtest yet, ...)."""


@dataclass
class LegResult:
    slug: str
    version: str
    weight: float
    stats: PerformanceStats


@dataclass
class CompositeBacktestResult:
    equity_curve: pd.Series
    drawdown: pd.Series
    returns: pd.Series
    stats: PerformanceStats
    legs: list[LegResult]
    total_leg_trades: int


def run_composite_backtest(
    legs: list[str], weighting: str = "inverse_vol", initial_capital: float = 100_000.0
) -> CompositeBacktestResult:
    if len(legs) < 2:
        raise CompositeError("a composite needs at least 2 legs")
    if len(set(legs)) != len(legs):
        raise CompositeError("duplicate leg in composite")

    records = []
    for slug in legs:
        record = latest_record(slug)
        if record is None:
            raise CompositeError(f"no research record found for nickname {slug!r}")
        if not has_backtest_result(record):
            raise CompositeError(f"{slug!r} has no saved backtest yet -- run its backtest first")
        records.append(record)

    leg_backtests = {r.slug: load_backtest_result(r) for r in records}
    rets = pd.DataFrame({slug: bt.returns for slug, bt in leg_backtests.items()}).fillna(0.0)

    if weighting == "equal":
        w = pd.Series(1.0 / len(rets.columns), index=rets.columns)
    elif weighting == "inverse_vol":
        vol = rets.std().replace(0.0, pd.NA)
        inv = (1.0 / vol).fillna(0.0)
        total = float(inv.sum())
        w = inv / total if total else pd.Series(1.0 / len(rets.columns), index=rets.columns)
    else:
        raise CompositeError(f"unknown weighting {weighting!r} (expected 'inverse_vol' or 'equal')")

    combined_returns = (rets * w).sum(axis=1)
    equity = (1 + combined_returns).cumprod() * initial_capital
    drawdown = drawdown_series(equity)
    stats = performance_stats(combined_returns, equity)

    leg_results = [
        LegResult(
            slug=record.slug,
            version=record.version,
            weight=float(w[record.slug]),
            stats=leg_backtests[record.slug].stats,
        )
        for record in records
    ]
    total_leg_trades = sum((leg.stats.n_trades or 0) for leg in leg_results)

    return CompositeBacktestResult(
        equity_curve=equity,
        drawdown=drawdown,
        returns=combined_returns,
        stats=stats,
        legs=leg_results,
        total_leg_trades=total_leg_trades,
    )


def save_composite_backtest(record: CompositeRecord, result: CompositeBacktestResult) -> None:
    payload = {
        "stats": asdict(result.stats),
        "total_leg_trades": result.total_leg_trades,
        "legs": [
            {
                "slug": leg.slug,
                "version": leg.version,
                "weight": leg.weight,
                "stats": asdict(leg.stats),
            }
            for leg in result.legs
        ],
    }
    with open(record.backtest_results_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    frame = pd.DataFrame(
        {"equity": result.equity_curve, "drawdown": result.drawdown, "returns": result.returns}
    )
    frame.to_parquet(record.equity_curve_path)


def load_composite_backtest(record: CompositeRecord) -> CompositeBacktestResult:
    with open(record.backtest_results_path, encoding="utf-8") as f:
        payload = json.load(f)

    stats = PerformanceStats(**payload["stats"])
    legs = [
        LegResult(
            slug=leg["slug"],
            version=leg["version"],
            weight=leg["weight"],
            stats=PerformanceStats(**leg["stats"]),
        )
        for leg in payload["legs"]
    ]
    frame = pd.read_parquet(record.equity_curve_path)
    return CompositeBacktestResult(
        equity_curve=frame["equity"],
        drawdown=frame["drawdown"],
        returns=frame["returns"],
        stats=stats,
        legs=legs,
        total_leg_trades=payload["total_leg_trades"],
    )


def has_composite_backtest(record: CompositeRecord) -> bool:
    return record.backtest_results_path.exists() and record.equity_curve_path.exists()
