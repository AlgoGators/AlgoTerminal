"""Artifact audit: the honest real results, on a roll-free price series.

The quoted walk-forward headline runs on a panel built from yfinance
continuous front-month futures (CL=F/RB=F/HO=F). Those legs roll on
different dates, so the crack series carries scheduled level
discontinuities. The worst is the gasoline spec switch: RBOB lifts on
the first trading day of March in 19/19 years (mean +9.2%), and those
15 sessions carry ~40% of the reported P&L.

This script re-measures the identical strategies on a roll-free panel
built from EIA daily spot prices (WTI Cushing, NY Harbor gasoline,
NY Harbor ULSD) and reports both, side by side, with the artifact
windows removed.

Inputs (all produced by the scripts in this repo):
  results/walkforward_series.csv          fixed controls, futures panel
  results/walkforward_causal_series.csv   causal re-derived, futures panel
  results/spot_fixed_series.csv           fixed controls, roll-free spot
  results/spot_causal_series.csv          causal re-derived, roll-free spot

Run:  python scripts/artifact_audit.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
GAMMA = 0.5772
# 1136 configuration rows are visible across results/*.csv in this repo
# alone (plus 39 harnesses, branch cool/kelly grids, book_oos v2-v8, the
# v1 audit tree). 1000, the number the headline used, is a floor.
N_TRIALS_QUOTED = 1000
N_TRIALS_REAL = 1136


def deflated_sharpe(r: pd.Series, N: int) -> float:
    r = pd.Series(r).dropna()
    T = len(r)
    srd = r.mean() / r.std(ddof=1)
    sk, ku = r.skew(), r.kurt()
    V = (1 - sk * srd + (ku - 1) / 4 * srd ** 2) / (T - 1)
    if V <= 0:
        return float("nan")
    sr0 = np.sqrt(V) * ((1 - GAMMA) * sps.norm.ppf(1 - 1 / N)
                        + GAMMA * sps.norm.ppf(1 - 1 / (N * np.e)))
    denom = np.sqrt(max(1 - sk * srd + (ku - 1) / 4 * srd ** 2, 1e-12))
    return float(sps.norm.cdf((srd - sr0) * np.sqrt(T - 1) / denom))


def metrics(r: pd.Series) -> dict:
    r = pd.Series(r).dropna()
    n = len(r)
    m, sd = r.mean(), r.std(ddof=1)
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    pa = np.arange(n)
    sums = np.array([r[pa // 20 == b].sum() for b in range(pa.max() // 20 + 1)
                     if (pa // 20 == b).sum() == 20])
    tb = float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums)))) if len(sums) >= 5 else np.nan
    return {"ann": m * 252 * 100, "sh": m / sd * np.sqrt(252), "dd": dd * 100, "tb": tb,
            "dsr_q": deflated_sharpe(r, N_TRIALS_QUOTED),
            "dsr_r": deflated_sharpe(r, N_TRIALS_REAL)}


def artifact_masks(idx: pd.DatetimeIndex) -> dict[str, pd.Series]:
    months = pd.Series(idx, index=idx).groupby([idx.year, idx.month])
    firsts = set(pd.to_datetime(months.first().values))
    lasts = set(pd.to_datetime(months.last().values))
    roll = set()
    for i, d in enumerate(idx):
        if d in firsts or d in lasts:
            roll.add(d)
        if i > 0 and idx[i - 1] in firsts:
            roll.add(d)
        if i + 1 < len(idx) and idx[i + 1] in firsts:
            roll.add(d)
    return {
        "as reported": pd.Series(False, index=idx),
        "ex March 1": pd.Series([d in firsts and d.month == 3 for d in idx], index=idx),
        "ex roll-window": pd.Series([d in roll for d in idx], index=idx),
        "ex top 1% days": pd.Series(False, index=idx),  # filled per series
    }


def real_round_trip_cost() -> dict:
    """Real round-trip cost of one 1,000 bbl 3:2:1 crack-spread unit.

    Published components (2025):
      exchange + clearing, NYMEX energy, non-member: $1.60 per contract per side
      NFA assessment fee:                            $0.02 per contract per side
      retail commission:                             $0 to $2.50 per side
      slippage: one tick round trip (cross half the bid-ask each way)

    One crack unit = 3 CL + 2 RB + 1 HO contracts = 1,000 bbl of spread.
    Tick values: CL $10.00, RB $4.20, HO $4.20.
    """
    exchange, nfa = 1.60, 0.02
    ticks = {"CL": (3, 10.00), "RB": (2, 4.20), "HO": (1, 4.20)}
    slip = sum(n * v for n, v in ticks.values())
    out = {}
    for comm in (0.0, 1.50, 2.50):
        fees = 12 * (exchange + nfa + comm)          # 6 contracts x 2 sides
        out[comm] = fees + slip
    return {"slippage_round_trip": slip, "by_commission": out}


def cost_sensitivity(series: dict, levels=(5, 10, 16, 24, 40)) -> None:
    """Recompute each saved series at higher per-side costs.

    The saved return is net of 5 bps per side, so gross = net +
    5bps*turnover and net(c) = gross - c*turnover. Turnover is |d pos|.
    """
    base_level = 19.19  # mean crack level, $/bbl, spot panel 2006-2024
    print("\n=== real round-trip cost of one 1,000 bbl 3:2:1 crack unit ===")
    rc = real_round_trip_cost()
    print(f"  slippage (3 CL + 2 RB + 1 HO, one tick round trip): ${rc['slippage_round_trip']:.2f}")
    for comm, tot in rc["by_commission"].items():
        per_bbl = tot / 1000.0
        bps_side = (per_bbl / base_level) * 10000 / 2
        print(f"  commission ${comm:.2f}/side -> total ${tot:.2f} = ${per_bbl:.4f}/bbl "
              f"= {bps_side:.1f} bps per side")
    print(f"  harness assumption: 5 bps per side = ${0.0005 * base_level:.4f}/bbl "
          f"= ${2 * 0.0005 * base_level:.4f}/bbl round trip")

    print("\n=== cost sensitivity (spot panel, roll-free) ===")
    hdr = f"{'series':<34}" + "".join(f"{c:>6}bps" for c in levels)
    print(hdr)
    for label, fname in series.items():
        if "spot" not in label and "contiguous" not in label:
            continue
        d = pd.read_csv(ROOT / "results" / fname, parse_dates=["date"]).set_index("date")
        turn = d["pos"].diff().abs().fillna(0.0)
        gross = d["ret"] + 0.0005 * turn
        row = f"{label:<34}"
        for c in levels:
            net = gross - (c / 10000.0) * turn
            m = metrics(net)
            row += f"{m['tb']:>+9.2f}"
        print(row)
    print("  (cells are block t at that per-side cost level)")


def main() -> None:
    series = {
        "FIXED controls / futures (quoted)": "walkforward_series.csv",
        "CAUSAL re-derived / futures (quoted)": "walkforward_causal_series.csv",
        "FIXED controls / roll-free spot": "spot_fixed_series.csv",
        "CAUSAL re-derived / roll-free spot": "spot_causal_series.csv",
        "CAUSAL contiguous-crush / futures": "wf_crush_futures_series.csv",
        "CAUSAL contiguous-crush / roll-free spot": "wf_crush_spot_series.csv",
    }
    hdr = f"{'strategy / panel':<38}{'exclusion':<16}{'ann':>9}{'Sharpe':>9}{'MaxDD':>9}{'block t':>9}{'DSR@1e3':>9}{'DSR@1.1e3':>11}"
    print(hdr)
    print("-" * len(hdr))
    for label, fname in series.items():
        d = pd.read_csv(ROOT / "results" / fname, parse_dates=["date"]).set_index("date")
        r = d["ret"]
        masks = artifact_masks(r.index)
        top1 = r.abs() > r.abs().quantile(0.99)
        masks["ex top 1% days"] = top1
        for name, mask in masks.items():
            m = metrics(r[~mask])
            tag = label if name == "as reported" else ""
            print(f"{tag:<38}{name:<16}{m['ann']:>+8.2f}%{m['sh']:>9.3f}{m['dd']:>+8.2f}%"
                  f"{m['tb']:>+9.2f}{m['dsr_q']:>9.3f}{m['dsr_r']:>11.3f}")
        print()

    cost_sensitivity(series)


if __name__ == "__main__":
    main()
