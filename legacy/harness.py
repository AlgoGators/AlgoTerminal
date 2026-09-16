"""Standalone research harness for the crack-spread mean-reversion strategy.

Pulls the real CL=F / RB=F / HO=F panel, builds the 3:2:1 crack spread,
runs the strategy module (generate_signals -> size_positions ->
apply_risk_rules), and reports full performance stats, drawdown episodes,
and trade-level diagnostics.

Usage:
    python harness.py [--start 2023-09-08] [--end 2026-09-08] [--strategy path]
"""

from __future__ import annotations

import argparse
import importlib.util
import sys

import numpy as np
import pandas as pd

from algoterminal.analytics.stats import (
    drawdown_periods,
    drawdown_series,
    performance_stats,
)

TICKERS = {"CL": "CL=F", "RB": "RB=F", "HO": "HO=F"}
# RB/HO are USD/gallon, CL is USD/barrel -> convert products to per-barrel.
GALLONS_PER_BARREL = 42.0
CRACK_WEIGHTS = {"RB": 2.0 / 3.0, "HO": 1.0 / 3.0}


def load_strategy(path: str):
    spec = importlib.util.spec_from_file_location("crack_strategy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_panel(start: str, end: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    panel = {}
    for name, ticker in TICKERS.items():
        raw = yf.download(
            ticker,
            start=start,
            end=pd.Timestamp(end) + pd.Timedelta(days=1),
            progress=False,
            auto_adjust=False,
            multi_level_index=False,
        )
        if raw.empty:
            print(f"WARN: no data for {name} ({ticker})")
            panel[name] = pd.DataFrame()
            continue
        raw = raw.rename(columns={"Close": "close"})
        panel[name] = raw[["close"]].sort_index()
        print(f"  {name:3s} {ticker:6s} rows={len(raw):5d} {raw.index.min().date()} -> {raw.index.max().date()}")
    return panel


def build_crack(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join the three legs and compute the per-barrel 3:2:1 crack spread."""
    legs = {name: df["close"] for name, df in panel.items() if not df.empty}
    closes = pd.DataFrame(legs).sort_index()
    product = sum(closes[sym] * w for sym, w in CRACK_WEIGHTS.items() if sym in closes)
    crack = product * GALLONS_PER_BARREL - closes["CL"]
    closes["crack"] = crack
    return closes


def run_strategy(strategy, prices: pd.DataFrame) -> pd.DataFrame:
    signal = strategy.generate_signals(prices)
    sized = strategy.size_positions(signal, prices)
    positions = strategy.apply_risk_rules(sized, prices)
    positions = positions.reindex(prices.index).fillna(0.0)

    crack = prices["crack"]
    if isinstance(positions, pd.DataFrame):
        # Multi-leg book: returns = sum over legs of leg_pos * that leg's own return.
        if hasattr(strategy, "leg_levels"):
            levels = strategy.leg_levels(prices)
        else:
            levels = {col: crack for col in positions.columns}
        strategy_returns = sum(
            positions[col].shift(1).fillna(0.0) * levels[col].pct_change().fillna(0.0)
            for col in positions.columns
        )
        # Rebuild a flat "position" view for reporting: exposure proxy.
        flat_pos = positions.abs().sum(axis=1)
    else:
        asset_returns = crack.pct_change().fillna(0.0)
        strategy_returns = positions.shift(1).fillna(0.0) * asset_returns
        flat_pos = positions

    equity = (1 + strategy_returns).cumprod() * 100_000.0
    drawdown = drawdown_series(equity)
    performance_stats(strategy_returns, equity, flat_pos)

    return pd.DataFrame(
        {
            "crack": crack,
            "signal": signal if isinstance(signal, pd.Series) else signal.abs().sum(axis=1),
            "position": flat_pos,
            "returns": strategy_returns,
            "equity": equity,
            "drawdown": drawdown,
        }
    )


def trade_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Split the position series into discrete trades with entry/exit and PnL."""
    pos = frame["position"].fillna(0.0)
    ret = frame["returns"].fillna(0.0)
    trades = []
    entry_i = None
    entry_side = None
    for i in range(len(pos)):
        p = pos.iloc[i]
        side = 1 if p > 0 else (-1 if p < 0 else 0)
        if entry_i is None and side != 0:
            entry_i = i
            entry_side = side
        elif entry_i is not None and side != entry_side:
            pnl = ret.iloc[entry_i : i + 1].sum()
            trades.append(
                {
                    "entry": frame.index[entry_i].date(),
                    "exit": frame.index[i].date(),
                    "side": entry_side,
                    "bars": i - entry_i,
                    "pnl": pnl,
                }
            )
            entry_i = i if side != 0 else None
            entry_side = side if side != 0 else None
    if entry_i is not None:
        pnl = ret.iloc[entry_i:].sum()
        trades.append(
            {
                "entry": frame.index[entry_i].date(),
                "exit": frame.index[-1].date(),
                "side": entry_side,
                "bars": len(pos) - entry_i,
                "pnl": pnl,
            }
        )
    return pd.DataFrame(trades)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-09-08")
    ap.add_argument("--end", default="2026-09-08")
    ap.add_argument("--strategy", default="strategy.py")
    args = ap.parse_args()

    print("Fetching panel...")
    panel = fetch_panel(args.start, args.end)
    closes = build_crack(panel)
    if "crack" not in closes or closes["crack"].dropna().empty:
        print("FATAL: cannot construct a crack spread from available data")
        sys.exit(1)

    print(f"\nCrack spread: {closes['crack'].dropna().index.min().date()} -> "
          f"{closes['crack'].dropna().index.max().date()}  n={len(closes['crack'].dropna())}")
    print(f"  level  mean={closes['crack'].mean():.2f}  std={closes['crack'].std():.2f}  "
          f"min={closes['crack'].min():.2f}  max={closes['crack'].max():.2f}")

    strategy = load_strategy(args.strategy)
    frame = run_strategy(strategy, closes)

    s = frame["returns"]
    st = frame["equity"].iloc[-1] / frame["equity"].iloc[0] - 1
    years = len(s) / 252
    cagr = (frame["equity"].iloc[-1] / frame["equity"].iloc[0]) ** (1 / years) - 1
    daily_std = s.std()
    sharpe = s.mean() / daily_std * np.sqrt(252) if daily_std else 0.0
    downside = s[s < 0].std()
    sortino = s.mean() / downside * np.sqrt(252) if downside else 0.0

    trades = trade_summary(frame)
    wins = trades[trades["pnl"] > 0] if not trades.empty else trades
    win_rate = len(wins) / len(trades) if len(trades) else 0.0

    print("\n=== CURRENT STRATEGY ON REAL CRACK SPREAD ===")
    print(f"  CAGR      {cagr:8.2%}")
    print(f"  Sharpe    {sharpe:8.2f}")
    print(f"  Sortino   {sortino:8.2f}")
    print(f"  Max DD    {frame['drawdown'].min():8.2%}")
    print(f"  Total     {st:8.2%}")
    print(f"  Win rate  {win_rate:8.2%}   ({len(wins)}/{len(trades)})")
    print(f"  Trades    {len(trades):8d}")
    print(f"  Exposure  {frame['position'].abs().mean():8.2%}")

    dd = drawdown_periods(frame["equity"], top_n=5)
    if not dd.empty:
        print("\nWorst drawdowns:")
        for _, r in dd.iterrows():
            print(f"  {r['start'].date()} -> {r['trough'].date()}  depth={r['depth']:.2%}  "
                  f"len={r['length_days']}d  recovered={r['recovered']}")

    if not trades.empty:
        worst = trades.nsmallest(5, "pnl")
        print("\nWorst trades:")
        for _, r in worst.iterrows():
            print(f"  {r['entry']} -> {r['exit']}  side={'L' if r['side']>0 else 'S'}  "
                  f"{r['bars']}d  pnl={r['pnl']:.2%}")

    # Tail-event scan: largest single-bar crack moves and what the strategy did
    print("\nLargest single-bar crack moves (tail events):")
    moves = frame["crack"].diff().abs().nlargest(8)
    for idx, mv in moves.items():
        pos = frame["position"].loc[idx]
        ret = frame["returns"].loc[idx]
        print(f"  {idx.date()}  |dCrack|={mv:6.2f}  pos={pos:+.2f}  strat_ret={ret:+.2%}")


if __name__ == "__main__":
    main()
