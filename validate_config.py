"""Detailed validation of the headline config (CORE3 EQ NOCAP + overlay) + robustness."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
spec = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b4)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

df = pd.read_parquet(b4.PANEL).sort_index()
levels = fb.build_levels(df)
factors, rets, turn = b4.build_v4(levels, None)
net = b4.apply_costs(factors, rets, turnover=turn)
isw = b4.window(net, b4.IS_START, df.index.max())
oos = b4.window(net, b4.OOS_START, b4.IS_START)

w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
print("CORE3 EQ weights:", {k: round(v, 3) for k, v in w.items()})
book = b4.book_returns(net, b4.SUBSETS["CORE3"], w)
b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
ob_is, ob_oos = b4.apply_overlay(b_is), b4.apply_overlay(b_oos)

print("\nIS :", {k: round(v, 3) for k, v in b4.stats(b_is).items() if k != "cagr" or True})
print("IS raw   : CAGR %.2f%% Sharpe %.2f DD %.2f%% vol %.1f%%" % (
    b4.stats(b_is)["cagr"] * 100, b4.stats(b_is)["sharpe"],
    b4.stats(b_is)["maxdd"] * 100, b4.stats(b_is)["vol"] * 100))
print("IS overlay: CAGR %.2f%% Sharpe %.2f DD %.2f%% vol %.1f%%" % (
    b4.stats(ob_is)["cagr"] * 100, b4.stats(ob_is)["sharpe"],
    b4.stats(ob_is)["maxdd"] * 100, b4.stats(ob_is)["vol"] * 100))
print("OOS raw   : CAGR %.2f%% Sharpe %.2f DD %.2f%% vol %.1f%%" % (
    b4.stats(b_oos)["cagr"] * 100, b4.stats(b_oos)["sharpe"],
    b4.stats(b_oos)["maxdd"] * 100, b4.stats(b_oos)["vol"] * 100))
print("OOS overlay: CAGR %.2f%% Sharpe %.2f DD %.2f%% vol %.1f%% worst %.2f%%" % (
    b4.stats(ob_oos)["cagr"] * 100, b4.stats(ob_oos)["sharpe"],
    b4.stats(ob_oos)["maxdd"] * 100, b4.stats(ob_oos)["vol"] * 100,
    b4.stats(ob_oos)["worst_day"] * 100))

# --- yearly OOS (raw vs overlay) ----
print("\nYearly OOS (CORE3 EQ):")
for y, g in b_oos.groupby(b_oos.index.year):
    rs, os = b4.stats(g), b4.stats(ob_oos.loc[g.index])
    print("  %4d  raw %+7.2f%%  (Sh %5.2f)   ov %+7.2f%%  (Sh %5.2f)" % (
        y, g.sum() * 100, rs["sharpe"], ob_oos.loc[g.index].sum() * 100, os["sharpe"]))

# --- worst OOS days raw and overlaid ----
print("\nWorst OOS days raw:")
for idx, v in b_oos.nsmallest(8).items():
    print("  %s  %+7.2f%%" % (idx.date(), v * 100))
print("Worst OOS days overlay:")
for idx, v in ob_oos.nsmallest(8).items():
    print("  %s  %+7.2f%%" % (idx.date(), v * 100))

# --- 2013 attribution per factor (corrected) ----
y13 = oos.loc["2013"]
print("\n2013 per-factor (v4 corrected):")
for f in oos.columns:
    pos = factors[f].loc[y13.index]
    print("  %-16s ret %+8.2f%%  daysOn %.1f%%" % (f, y13[f].sum() * 100, (pos.abs() > 0).mean() * 100))

# --- 2019/2020 attribution ----
for yr in ["2019", "2020"]:
    g = oos.loc[yr]
    print("\n%s per-factor:" % yr)
    for f in oos.columns:
        print("  %-16s ret %+8.2f%%" % (f, g[f].sum() * 100))

# --- robustness: overlay thresholds on OOS (CORE3 EQ) ----
print("\nOverlay threshold sensitivity OOS (CORE3 EQ):")
for cut_, halt_, vt_ in [(-0.06, -0.10, 0.10), (-0.05, -0.09, 0.10), (-0.075, -0.12, 0.10),
                         (-0.04, -0.08, 0.10), (-0.06, -0.10, 0.08), (-0.06, -0.10, 0.12)]:
    ob = b4.apply_overlay(b_oos, vol_target=vt_, cut=cut_, halt=halt_)
    s = b4.stats(ob)
    print("  cut %5.3f halt %5.3f vt %.2f | Sh %5.2f CAGR %7.2f%% DD %7.2f%% vol %5.1f%% worst %6.2f%%" % (
        cut_, halt_, vt_, s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100, s["vol"] * 100, s["worst_day"] * 100))

# --- weight robustness: EQ vs HLV vs INV with overlay vs without (CORE3, NOCAP) ----
print("\nWeight scheme robustness (CORE3 NOCAP, with overlay):")
for scheme in ["EQ", "HLV", "INV"]:
    wq = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], scheme)
    bk = b4.book_returns(net, b4.SUBSETS["CORE3"], wq)
    for ov in [0, 1]:
        bo = b4.apply_overlay(bk.loc[oos.index]) if ov else bk.loc[oos.index]
        s = b4.stats(bo)
        print("  %-4s ov=%d | IS Sh %5.2f | OOS Sh %5.2f CAGR %7.2f%% DD %7.2f%% vol %5.1f%%" % (
            scheme, ov, b4.stats(b4.apply_overlay(bk.loc[isw.index]) if ov else bk.loc[isw.index])["sharpe"],
            s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100, s["vol"] * 100))

# --- DDs summary: raw CORE3 at fixed 10% vol (report normalization) + overlay at natural ----
print("\nComparable at 10% vol (reporting normalization, not a trading rule):")
for label, s in [("raw CORE3 EQ", b_oos), ("overlay CORE3 EQ", ob_oos)]:
    v = s.std() * np.sqrt(252)
    scaled = s * (0.10 / v)
    st = b4.stats(scaled)
    print("  %-20s Sharpe %5.2f  MaxDD %7.2f%%  CAGR %7.2f%%" % (
        label, st["sharpe"], st["maxdd"] * 100, st["cagr"] * 100))