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


if __name__ == "__main__":
    main()
