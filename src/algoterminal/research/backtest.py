"""The "Backtest" stage: a small, dependency-free vectorized backtest engine.

Runs the user's scaffolded strategy (generate_signals -> size_positions ->
apply_risk_rules) against pulled price data and produces an equity curve,
drawdown series, and a stats table.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from types import ModuleType

import numpy as np
import pandas as pd

from algoterminal.analytics.stats import PerformanceStats, drawdown_series, performance_stats
from algoterminal.research.storage import ResearchRecord

BacktestStats = PerformanceStats


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    drawdown: pd.Series
    positions: pd.Series
    returns: pd.Series
    stats: BacktestStats


_LEVEL_ANCHOR_WINDOW = 252  # ~1 trading year


def run_backtest(
    strategy: ModuleType,
    prices: pd.Series,
    initial_capital: float = 100_000.0,
    is_level: bool = False,
    cost_bps: float = 0.0,
) -> BacktestResult:
    """Run a strategy against a price (or level) series.

    `is_level` must be True for series that aren't themselves tradable
    prices -- spreads, bases, and other differenced levels (e.g. the
    crack-spread `derived` source), which can sit near/below zero. For
    those, pct_change() is undefined/unstable and misweights equal $-moves
    differently depending on the level, so returns are instead the day's
    level change against a slowly-adapting reference (a trailing rolling
    mean of the level's magnitude, expanding during the warmup period) --
    not a single fixed value pinned to whatever the level happened to be on
    day 1, which would make "1.0x position" mean a different $ exposure
    purely depending on when the backtest window happened to start.

    `cost_bps` applies a simple turnover-based cost: `cost_bps` per 1.0 of
    |position change| (so a full flip from -1 to +1 costs 2x), deducted
    from that day's return. This is a rough estimate, not a real execution
    model (no bid-ask by instrument, no market impact, no distinction
    between a same-day resize and a fresh entry) -- default 0.0 preserves
    prior behavior; pass a nonzero estimate to see cost-adjusted numbers.
    """
    prices = prices.dropna()

    signal = strategy.generate_signals(prices)
    sized = strategy.size_positions(signal, prices)
    positions = strategy.apply_risk_rules(sized, prices)
    positions = positions.reindex(prices.index).fillna(0.0)

    if is_level:
        level = prices.abs()
        anchor = level.rolling(_LEVEL_ANCHOR_WINDOW, min_periods=20).mean().shift(1)
        anchor = anchor.fillna(level.expanding(min_periods=1).mean().shift(1))
        anchor = anchor.replace(0.0, np.nan).ffill().bfill().fillna(1.0)
        asset_returns = (prices.diff() / anchor).fillna(0.0)
    else:
        asset_returns = prices.pct_change().fillna(0.0)
    strategy_returns = positions.shift(1).fillna(0.0) * asset_returns

    if cost_bps:
        turnover = positions.diff().abs().fillna(positions.abs().iloc[0] if len(positions) else 0.0)
        strategy_returns = strategy_returns - turnover * (cost_bps / 10_000.0)

    equity = (1 + strategy_returns).cumprod() * initial_capital
    drawdown = drawdown_series(equity)
    stats = performance_stats(strategy_returns, equity, positions)

    return BacktestResult(
        equity_curve=equity,
        drawdown=drawdown,
        positions=positions,
        returns=strategy_returns,
        stats=stats,
    )


def save_backtest_result(record: ResearchRecord, result: BacktestResult) -> None:
    with open(record.backtest_results_path, "w", encoding="utf-8") as f:
        json.dump(asdict(result.stats), f, indent=2)

    frame = pd.DataFrame(
        {
            "equity": result.equity_curve,
            "drawdown": result.drawdown,
            "positions": result.positions,
            "returns": result.returns,
        }
    )
    frame.to_parquet(record.equity_curve_path)


def load_backtest_result(record: ResearchRecord) -> BacktestResult:
    """Reload a previously saved backtest run without re-running it."""
    with open(record.backtest_results_path, encoding="utf-8") as f:
        stats = BacktestStats(**json.load(f))

    frame = pd.read_parquet(record.equity_curve_path)
    return BacktestResult(
        equity_curve=frame["equity"],
        drawdown=frame["drawdown"],
        positions=frame["positions"],
        returns=frame["returns"],
        stats=stats,
    )


def has_backtest_result(record: ResearchRecord) -> bool:
    return record.backtest_results_path.exists() and record.equity_curve_path.exists()
