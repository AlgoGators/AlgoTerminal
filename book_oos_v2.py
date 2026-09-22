"""Book v2 — OOS-focused construction: factor subset + robust weights + DD overlay.

Question: which factor subset, weight scheme (trained on IS only), and book-level
vol/DD overlay give the best OOS behavior with MaxDD capped near ~10%?

Baseline from LONG_BACKTEST_FINDINGS.md:
- 5-factor book, IS-frozen inverse-vol weights: OOS Sharpe 0.46, MaxDD -21.9% at ~9.5% vol.
- Equal weight OOS Sharpe 0.51 (beats inverse-vol 0.46).
- OOS failures: crack_ho (-0.08), ng (0.11), bzwti (0.25 vs 1.53 IS).

Design:
- Factor subsets:
    FULL  {crack_321, crack_ho, cross_sectional, ng, bzwti}
    NOHO  {crack_321, cross_sectional, ng, bzwti}
    CORE3 {crack_321, cross_sectional, bzwti}
    CORE2 {crack_321, cross_sectional}
    NGKEEP3 {crack_321, cross_sectional, ng}
- Weight schemes (trained on IS post-warm-up net returns ONLY, then frozen):
    EQ   equal weights
    INV  inverse-vol raw  w_i ~ 1/sigma_i
    HLV  inverse-vol half-shrunk w_i ~ (1/sigma_i)^0.5  (toward equal)
- Book-level overlay (causal, weights frozen, no OOS leakage):
    vol gear:  scale = min(1, VOL_TARGET / trailing 20d realized vol)  (shifted)
    DD de-lever: measured on the UNDERLYING (ungeared) book drawdown:
         dd <= CUT   -> scale 0.5
         dd <= HALT  -> scale 0.0
         resume full when dd recovers above REENTER
    Defaults are a stated risk policy, not fitted to OOS: CUT -7.5%, HALT -10%, REENTER -4%.
- Reporting: per subset x scheme x overlay, IS & OOS Sharpe/CAGR/MaxDD/worstDay/vol.
  Plus yearly OOS table for CORE3-HLV-DD, 2013 attribution, and overlay sensitivity.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = (Path("/tmp/panel_adj_2007_2026.parquet")
         if Path("/tmp/panel_adj_2007_2026.parquet").exists()
         else Path(__file__).resolve().parent / "panel_v2.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90
TRADE_BPS = 5.0
ROLL_BPS = 20.0

spec = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

spec2 = importlib.util.spec_from_file_location("lb", str(DEV / "long_backtest.py"))
lb = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(lb)

SUBSETS = {
    "FULL": ["crack_321", "crack_ho", "cross_sectional", "ng", "bzwti"],
    "NOHO": ["crack_321", "cross_sectional", "ng", "bzwti"],
    "CORE3": ["crack_321", "cross_sectional", "bzwti"],
    "CORE2": ["crack_321", "cross_sectional"],
    "NGKEEP3": ["crack_321", "cross_sectional", "ng"],
}


def load_panel() -> pd.DataFrame:
    return pd.read_parquet(PANEL).sort_index()


def build_all(levels):
    """Positions + corrected-return series for all 5 factors (reuses long_backtest)."""
    return lb.build_positions_and_returns(levels)


def weight_scheme(returns_is: pd.DataFrame, scheme: str) -> dict[str, float]:
    """Weights from IS-window net returns. All sum to 1 within the subset."""
    vols = returns_is.std().replace(0.0, np.nan)
    if scheme == "EQ":
        w = pd.Series(1.0, index=returns_is.columns)
    elif scheme == "INV":
        w = 1.0 / vols
    elif scheme == "HLV":
        w = (1.0 / vols) ** 0.5
    else:
        raise ValueError(scheme)
    return (w / w.sum()).to_dict()


def book_returns(net: pd.DataFrame, factors: list[str], weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=net.index)
    for f in factors:
        s = s + weights[f] * net[f]
    return s


def drawdown(s: pd.Series) -> pd.Series:
    eq = (1 + s).cumprod()
    return eq / eq.cummax() - 1


def apply_overlay(book: pd.Series, vol_target: float = 0.10,
                  cut: float = -0.075, halt: float = -0.10,
                  reenter: float = -0.04) -> pd.Series:
    """Causal book-level vol gear + drawdown de-lever.

    gear_t uses trailing 20d realized vol through t-1 (shifted), clipped to 100%.
    dd policy: a hysteresis state machine driven by the UNDERLYING (ungeared)
    book drawdown through t-1:
        FULL(1.0) --[dd <= cut]--> CAUTION(0.5) --[dd <= halt]--> HALT(0.0)
        CAUTION --[dd > reenter]--> FULL ;  HALT --[dd > reenter]--> FULL
    Scale applied to day-t return: gear_{t-1} * policy_{t-1}.
    """
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    dd = drawdown(book)
    dd_prev = dd.shift(1)
    policy = np.ones(len(book), dtype=float)
    state = 1.0
    ddp = dd_prev.to_numpy(dtype=float)
    for i in range(len(book)):
        if np.isnan(ddp[i]):
            policy[i] = state
            continue
        d = ddp[i]
        if state == 1.0:
            if d <= cut:
                state = 0.5
        elif state == 0.5:
            if d <= halt:
                state = 0.0
            elif d > reenter:
                state = 1.0
        else:  # halted
            if d > reenter:
                state = 1.0
        policy[i] = state
    scale = pd.Series(gear.to_numpy() * policy, index=book.index).shift(1).fillna(1.0)
    return book * scale


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan,
                "worst_day": np.nan, "vol": np.nan, "total": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / years) - 1
    return {"cagr": cagr, "sharpe": r.mean() / r.std() * np.sqrt(252),
            "maxdd": (eq / eq.cummax() - 1).min(), "worst_day": r.min(),
            "vol": r.std() * np.sqrt(252), "total": eq.iloc[-1] - 1}


def window(r: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = r.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out


def fmt(v) -> str:
    return "      --" if pd.isna(v) else ("%7.2f%%" % (v * 100))


def main() -> None:
    df = load_panel()
    levels = fb.build_levels(df)
    print("Building positions/returns (corrected basis, 5 factors)...")
    positions, rets = build_all(levels)
    net = lb.apply_costs(positions, rets, TRADE_BPS, ROLL_BPS)

    oos = window(net, OOS_START, IS_START)
    isw = window(net, IS_START, df.index.max())

    schemes = ["EQ", "INV", "HLV"]
    print("\nIS-window vols (post-warm-up, net):")
    for f in net.columns:
        print("  %-16s %.3f" % (f, isw[f].std()))

    results = []
    print("\n=== SUB-SET x WEIGHT x OVERLAY: IS and OOS ===")
    print("%-7s %-4s %-4s | %-8s %-8s %-8s | %-8s %-8s %-8s %-8s" % (
        "subset", "wt", "ov", "IS_Sh", "IS_DD", "OOS_Sh", "OOS_CAGR", "OOS_DD", "OOS_vol", "worstDay"))
    for sname, factors in SUBSETS.items():
        for scheme in schemes:
            w = weight_scheme(isw[factors], scheme)
            book = book_returns(net, factors, w)
            b_is = book.loc[isw.index]
            b_oos = book.loc[oos.index]
            for ov in [False, True]:
                b_is_o = apply_overlay(b_is) if ov else b_is
                b_oos_o = apply_overlay(b_oos) if ov else b_oos
                si, so = stats(b_is_o), stats(b_oos_o)
                results.append({"subset": sname, "scheme": scheme, "overlay": ov,
                                "IS_sharpe": si["sharpe"], "IS_maxdd": si["maxdd"],
                                "OOS_sharpe": so["sharpe"], "OOS_cagr": so["cagr"],
                                "OOS_maxdd": so["maxdd"], "OOS_vol": so["vol"],
                                "OOS_worst": so["worst_day"]})
                print("%-7s %-4s %-4s | %8.2f %8s | %8.2f %8s %8s %8s" % (
                    sname, scheme, "DD" if ov else "--",
                    si["sharpe"], fmt(si["maxdd"]),
                    so["sharpe"], fmt(so["cagr"]), fmt(so["maxdd"]), fmt(so["vol"])))

    res = pd.DataFrame(results)
    res.to_csv(DEV / "book_oos_v2_results.csv", index=False)
    print("\nSaved table to book_oos_v2_results.csv")

    # ---- CORE3 HLV with overlay: detailed view ----
    def show(sname: str, scheme: str, ov: bool, label: str):
        factors = SUBSETS[sname]
        w = weight_scheme(isw[factors], scheme)
        book = book_returns(net, factors, w)
        print("\n=== %s (%s weights) ===" % (label, scheme.upper()))
        print("  weights:", ", ".join("%s=%.3f" % (f, w[f]) for f in factors))
        b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
        for name, b in [("IS ", b_is), ("OOS", b_oos)]:
            b2 = apply_overlay(b) if ov else b
            s = stats(b2)
            a = stats(b)
            print("  %s raw      : CAGR=%s Sharpe=%5.2f MaxDD=%s vol=%s worstDay=%s" % (
                name, fmt(a["cagr"]), a["sharpe"], fmt(a["maxdd"]), fmt(a["vol"]), fmt(a["worst_day"])))
            print("  %s overlay  : CAGR=%s Sharpe=%5.2f MaxDD=%s vol=%s worstDay=%s" % (
                name, fmt(s["cagr"]), s["sharpe"], fmt(s["maxdd"]), fmt(s["vol"]), fmt(s["worst_day"])))

    show("CORE3", "HLV", True, "CORE3 (321 + cross + bzwti)")

    # ---- yearly OOS for CORE3 HLV DD ----
    factors = SUBSETS["CORE3"]
    w = weight_scheme(isw[factors], "HLV")
    book = book_returns(net, factors, w)
    b_oos = book.loc[oos.index]
    ob = apply_overlay(b_oos)
    print("\nYearly OOS (CORE3 HLV with DD overlay): raw vs overlay")
    for y, g in b_oos.groupby(b_oos.index.year):
        rs = stats(g)
        os = stats(ob.loc[g.index])
        print("  %4d  raw %+7.2f%%  (Sharpe %5.2f)   ov %+7.2f%%  (Sharpe %5.2f)" % (
            y, g.sum() * 100, rs["sharpe"], ob.loc[g.index].sum() * 100, os["sharpe"]))

    # ---- 2013 attribution: per-factor net returns by year ----
    print("\n=== 2013 attribution (per-factor net, OOS window) ===")
    y13 = oos.loc["2013"]
    print("  year 2013 total net return per factor:")
    for f in oos.columns:
        print("  %-16s %+8.2f%%" % (f, y13[f].sum() * 100))
    print("  days in market (2013):")
    for f in oos.columns:
        pos = positions[f].loc[y13.index]
        print("  %-16s %.1f%%" % (f, (pos.abs() > 0).mean() * 100))

    # ---- overlay sensitivity on OOS (CORE3 HLV) ----
    print("\n=== Overlay sensitivity on OOS CORE3 HLV (halt/cut/reenter) ===")
    print("  cut    halt   reenter | Sharpe  CAGR   MaxDD   vol")
    for cut_, halt_, re_ in [(-0.075, -0.10, -0.04),
                             (-0.05, -0.08, -0.03),
                             (-0.10, -0.15, -0.05),
                             (-0.075, -0.10, -0.02),
                             (np.nan, np.nan, np.nan)]:
        if np.isnan(cut_):
            s = stats(b_oos)
            print("  (no overlay)           | %5.2f  %6s  %7s  %6s" % (
                s["sharpe"], fmt(s["cagr"]), fmt(s["maxdd"]), fmt(s["vol"])))
            continue
        ob2 = apply_overlay(b_oos, vol_target=0.10, cut=cut_, halt=halt_, reenter=re_)
        s = stats(ob2)
        print("  %6.3f %6.3f %6.3f | %5.2f  %6s  %7s  %6s" % (
            cut_, halt_, re_, s["sharpe"], fmt(s["cagr"]), fmt(s["maxdd"]), fmt(s["vol"])))

    # ---- worst OOS days with overlay (CORE3 HLV) ----
    print("\nWorst OOS days — CORE3 HLV with overlay:")
    worst = ob.nsmallest(8)
    for idx, v in worst.items():
        print("  %s  %+7.2f%%" % (idx.date(), v * 100))


if __name__ == "__main__":
    main()