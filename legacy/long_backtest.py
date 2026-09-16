"""Honest long backtest of the factor book (factor_book.py) — v2.

Fixes over v1:
- Return basis bug: factor_book.main() prices PnL as pos * level.pct_change().
  That explodes whenever a level crosses zero (BZ-WTI crosses 548 times in
  2007-2026, crack_gas 60 times) -> phantom +/-inf returns. IS never hit it
  (BZ-WTI stayed positive 2023-26); the 16y OOS test is contaminated by it.
  Correct basis: pos.shift(1) * level.diff() / base.shift(1), where base =
  rolling mean of |level| — exactly the denominator the sizing math uses.
  This is the "spread-relative" return; identical to pct_change when the
  level is positive and stable, finite when the level crosses zero.
- Book construction: the recorded book is inverse-vol weighted, with weights
  computed on the IS post-warm-up returns. Honest version: freeze weights on
  IS, apply to OOS (walk-forward). Also report an equal-weight book.
- Books are also shown vol-normalized to 20% so MaxDD/CAGR are comparable.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = Path("/tmp/panel_adj_2007_2026.parquet")

IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90  # trading days dropped at the start of each window

TRADE_BPS = 5.0    # per side, on |position change| (default)
ROLL_BPS = 20.0    # annual drag on held notional (default)

spec = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)


def load_panel() -> pd.DataFrame:
    return pd.read_parquet(PANEL).sort_index()


def spread_ret(pos: pd.Series, level: pd.Series, base: pd.Series | None = None) -> pd.Series:
    """Spread-relative daily return, artifact-free near zero.

    ret_t = pos_{t-1} * (level_t - level_{t-1}) / base_{t-1}
    base (default) = rolling mean of |level| over VOL_LOOKBACK, shifted —
    the same denominator the vol-target sizing uses.
    """
    if base is None:
        base = level.abs().rolling(fb.VOL_LOOKBACK, min_periods=10).mean()
    d = level.diff()
    denom = base.shift(1).replace(0.0, np.nan)
    r = pos.shift(1).fillna(0.0) * d / denom
    return r.fillna(0.0)


def build_positions_and_returns(levels: dict[str, pd.Series]):
    """Return (positions, returns) with the corrected spread-relative basis."""
    factors = {}
    factors.update(fb.f1_positions(levels))
    factors.update(fb.f2_positions(levels))
    factors.update(fb.f3_positions(levels))
    factors.update(fb.f4_positions(levels))

    rets = {}
    for name, pos in factors.items():
        if name == "cross_sectional":
            legs = {
                "crack_321": levels["crack_321"],
                "crack_gas": levels["crack_gas"],
                "crack_ho": levels["crack_ho"],
            }
            zdf = pd.DataFrame({k: fb.seasonal_z(lvl) for k, lvl in legs.items()})
            arr = zdf.to_numpy(dtype=float)
            cols = list(zdf.columns)
            held_level = pd.Series(np.nan, index=pos.index)
            for i in range(len(zdf)):
                if pos.iloc[i] != 0.0 and not np.isnan(arr[i]).all():
                    held_level.iloc[i] = levels[cols[int(np.nanargmin(arr[i]))]].iloc[i]
            base = held_level.abs().rolling(fb.VOL_LOOKBACK, min_periods=10).mean()
            rets[name] = spread_ret(pos, held_level.fillna(levels["crack_321"]), base)
        else:
            rets[name] = spread_ret(pos, levels[name])
    return factors, rets


def apply_costs(positions, returns, trade_bps=TRADE_BPS, roll_bps=ROLL_BPS):
    out = {}
    for name in returns:
        pos = positions[name].fillna(0.0)
        dp = pos.diff().fillna(0.0).abs()
        trade_cost = trade_bps / 10000.0 * dp
        roll_cost = roll_bps / 252.0 / 10000.0 * pos.abs()
        out[name] = (returns[name] - trade_cost - roll_cost).fillna(0.0)
    return pd.DataFrame(out)


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan,
                "worst_day": np.nan, "total": np.nan, "vol": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / years) - 1
    sharpe = r.mean() / r.std() * np.sqrt(252)
    maxdd = (eq / eq.cummax() - 1).min()
    return {"cagr": cagr, "sharpe": sharpe, "maxdd": maxdd,
            "worst_day": r.min(), "total": eq.iloc[-1] - 1,
            "vol": r.std() * np.sqrt(252)}


def window(rets: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    r = rets.loc[start:end]
    return r.iloc[WARMUP:] if len(r) > WARMUP else r


def print_stats(df: pd.DataFrame, label: str) -> None:
    print(f"\n{label}")
    print("  %-16s %8s %7s %7s %9s %9s %6s" % ("factor", "CAGR", "Sharpe", "MaxDD", "worstDay", "annVol", "daysOn"))
    for name, row in df.iterrows():
        print("  %-16s %7.2f%% %7.2f %7.2f%% %+8.2f%% %6.1f%% %6.1f%%" % (
            name,
            row["cagr"] * 100 if pd.notna(row["cagr"]) else float("nan"),
            row["sharpe"] if pd.notna(row["sharpe"]) else float("nan"),
            row["maxdd"] * 100 if pd.notna(row["maxdd"]) else float("nan"),
            row["worst_day"] * 100 if pd.notna(row["worst_day"]) else float("nan"),
            row["vol"] * 100 if pd.notna(row["vol"]) else float("nan"),
            row["days_on"] * 100,
        ))


def build_book(weights: dict[str, float], net: pd.DataFrame) -> pd.Series:
    s = pd.Series(0.0, index=net.index)
    for name, w in weights.items():
        if name in net:
            s = s + w * net[name]
    return s


def main() -> None:
    print("Loading panel...")
    df = load_panel()
    levels = fb.build_levels(df)
    print("Window: %s -> %s  rows=%d" % (df.index.min().date(), df.index.max().date(), len(df)))

    print("Building positions/returns (corrected basis, frozen params)...")
    positions, rets = build_positions_and_returns(levels)
    net = apply_costs(positions, rets)

    # ---- per-factor OOS + IS ----
    oos = window(net, OOS_START, IS_START)
    isw = window(net, IS_START, df.index.max())

    rows_oos, rows_is = {}, {}
    for name in net.columns:
        pos = positions[name]
        po = pos.loc[oos.index]
        rows_oos[name] = stats(oos[name])
        rows_oos[name]["days_on"] = float((po.abs() > 0).mean())
        pi = pos.loc[isw.index]
        rows_is[name] = stats(isw[name])
        rows_is[name]["days_on"] = float((pi.abs() > 0).mean())
    print_stats(pd.DataFrame(rows_oos).T, "=== OUT-OF-SAMPLE 2007-07 -> 2023-09 (net @ 5bps/20roll) ===")
    print_stats(pd.DataFrame(rows_is).T, "=== IN-SAMPLE 2023-09 -> 2026-09 (tuning window, net) ===")

    # ---- book: frozen inverse-vol weights from IS ----
    is_vols = isw.std()
    w_inv = (1.0 / is_vols.replace(0.0, np.nan))
    w_inv = w_inv / w_inv.sum()
    print("\nIS-frozen inverse-vol weights (from IS post-warm-up vols):")
    for k, v in w_inv.items():
        print("  %-16s %.3f" % (k, v))

    book_oos_wf = build_book(w_inv.to_dict(), oos)
    book_is_wf = build_book(w_inv.to_dict(), isw)
    bok = stats(book_oos_wf)
    bik = stats(book_is_wf)
    print("\n=== BOOK (IS-frozen inverse-vol weights) ===")
    print("  OOS: CAGR=%7.2f%% Sharpe=%5.2f MaxDD=%7.2f%% vol=%5.1f%% worstDay=%+.2f%%" % (
        bok["cagr"] * 100, bok["sharpe"], bok["maxdd"] * 100, bok["vol"] * 100, bok["worst_day"] * 100))
    print("  IS : CAGR=%7.2f%% Sharpe=%5.2f MaxDD=%7.2f%% vol=%5.1f%% worstDay=%+.2f%%" % (
        bik["cagr"] * 100, bik["sharpe"], bik["maxdd"] * 100, bik["vol"] * 100, bik["worst_day"] * 100))

    # ---- equal-weight book, vol-normalized to 20% for comparability ----
    def normalize(s: pd.Series, target_vol: float = 0.20) -> pd.Series:
        v = s.std() * np.sqrt(252)
        return s * (target_vol / v) if v else s

    eq_oos = build_book({k: 1.0 for k in net.columns}, oos)
    eq_oos20 = normalize(eq_oos)
    eq_is20 = normalize(build_book({k: 1.0 for k in net.columns}, isw))
    eo = stats(eq_oos20)
    ei = stats(eq_is20)
    print("\n=== BOOK (equal weight, normalized to 20% ann vol) ===")
    print("  OOS: CAGR=%7.2f%% Sharpe=%5.2f MaxDD=%7.2f%% worstDay=%+.2f%%" % (
        eo["cagr"] * 100, eo["sharpe"], eo["maxdd"] * 100, eo["worst_day"] * 100))
    print("  IS : CAGR=%7.2f%% Sharpe=%5.2f MaxDD=%7.2f%% worstDay=%+.2f%%" % (
        ei["cagr"] * 100, ei["sharpe"], ei["maxdd"] * 100, ei["worst_day"] * 100))

    # ---- yearly on OOS (frozen-weight book, 20% vol) ----
    print("\nYearly (frozen-weight book, normalized 20%, OOS):")
    yrs = eq_oos20.groupby(eq_oos20.index.year).sum() * 100
    for y, v in yrs.items():
        print("  %4d  %+7.2f%%" % (y, v))

    # ---- worst OOS days (frozen-weight book) ----
    worst = book_oos_wf.nsmallest(10)
    print("\nWorst OOS days (frozen-weight book, raw vol):")
    for idx, v in worst.items():
        print("  %s  %+7.2f%%" % (idx.date(), v * 100))

    print("\n--- OOS correlation matrix (net factor returns) ---")
    print(oos.corr().round(2).to_string())

    # ---- cost sensitivity on OOS frozen-weight book ----
    print("\nCost sensitivity — OOS frozen-weight book (Sharpe/CAGR/MaxDD):")
    print("  trade_bps roll_bps Sharpe   CAGR    MaxDD")
    for tb in [0.0, 2.5, 5.0, 10.0, 20.0]:
        for rb in [0.0, 10.0, 20.0, 40.0]:
            n = apply_costs(positions, rets, tb, rb)
            b = build_book(w_inv.to_dict(), window(n, OOS_START, IS_START))
            s = stats(b)
            print("  %6.1f   %6.1f   %5.2f  %6.2f%%  %7.2f%%" % (
                tb, rb, s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100))

    # ---- parameter stability on OOS ----
    print("\nParameter-stability sweep on OOS (book Sharpe, net @ 5bps/20roll, frozen weights):")
    base = {
        "SMR_Z_LOOKBACK": fb.SMR_Z_LOOKBACK,
        "SMR_ENTRY": fb.SMR_ENTRY,
        "F4_ENTRY": fb.F4_ENTRY,
        "VT_F2": fb.VT_F2,
        "VT_F3": fb.VT_F3,
    }
    sweeps = {
        "SMR_Z_LOOKBACK": [60, 90, 120, 150, 180],
        "SMR_ENTRY": [0.5, 0.75, 1.0, 1.25],
        "F4_ENTRY": [0.75, 1.0, 1.5, 2.0],
        "VT_F2": [0.25, 0.5, 0.75],
        "VT_F3": [0.25, 0.5, 0.75],
    }
    for param, values in sweeps.items():
        print(f"\n  {param}  (frozen={base[param]}):")
        for v in values:
            setattr(fb, param, v)
            try:
                pos2, ret2 = build_positions_and_returns(levels)
                n2 = apply_costs(pos2, ret2)
                b2 = build_book(w_inv.to_dict(), window(n2, OOS_START, IS_START))
                s = stats(b2)
                print("    %-6s Sharpe=%5.2f  CAGR=%6.2f%%  MaxDD=%7.2f%%" % (
                    str(v), s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100))
            except Exception as e:
                print("    %-6s ERROR %s" % (str(v), e))
        setattr(fb, param, base[param])


if __name__ == "__main__":
    main()