"""Diagnostics for the honest assessment: saturation, concentration, regimes, selection."""
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


def count_trades(pos: pd.Series) -> int:
    side = np.sign(pos.fillna(0.0).to_numpy())
    tr = 0
    prev = 0
    for s in side:
        if s != 0:
            if prev == 0:
                tr += 1
            prev = s
        else:
            prev = 0
    return tr


df = pd.read_parquet(b4.PANEL).sort_index()
levels = fb.build_levels(df)
factors, rets, turn = b4.build_v4(levels, None)
net = b4.apply_costs(factors, rets, turnover=turn)
isw = b4.window(net, b4.IS_START, df.index.max())
oos = b4.window(net, b4.OOS_START, b4.IS_START)

print("=== 1. Position saturation: % of in-market days at MAX_LEV (1.0) ===")
for f in net.columns:
    p = factors[f]
    on = p.abs() > 0
    sat = (p.abs() >= 0.99) & on
    print("  %-16s onDays %5.1f%%  atMaxLev %5.1f%% of onDays" % (
        f, on.mean() * 100, (sat.sum() / on.sum() * 100) if on.sum() else 0))

print("\n=== 2. Trade counts OOS (distinct entries) ===")
for f in net.columns:
    print("  %-16s %5d trades over %d days" % (f, count_trades(factors[f].loc[oos.index]), len(oos)))

print("\n=== 3. OOS return concentration (raw CORE3 EQ book) ===")
w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
book = b4.book_returns(net, b4.SUBSETS["CORE3"], w)
b_oos = book.loc[oos.index]
years = b_oos.groupby(b_oos.index.year).sum()
total = b_oos.sum()
pos_years = years[years > 0]
print("  total OOS return: %+.2f%%" % (total * 100))
print("  top-5 positive years: %s" % ", ".join("%d(%+.1f%%)" % (y, v * 100) for y, v in pos_years.nlargest(5).items()))
print("  share of total from top-5 years: %.0f%%" % (pos_years.nlargest(5).sum() / total * 100))
print("  negative years: %s" % ", ".join("%d(%+.1f%%)" % (y, v * 100) for y, v in years[years < 0].items()))

print("\n=== 4. Rolling 3y Sharpe (raw CORE3 EQ, OOS) ===")
r3 = b_oos.rolling(756).apply(lambda x: x.mean() / x.std() * np.sqrt(252) if x.std() else np.nan, raw=True)
yr = r3.groupby(r3.index.year).last()
for y, v in yr.dropna().items():
    print("  %4d  %+6.2f" % (y, v))

print("\n=== 5. Selection-on-OOS honesty: FULL vs CORE3 (EQ, overlay) ===")
for sname in ["FULL", "CORE3"]:
    wq = b4.weight_scheme(isw[b4.SUBSETS[sname]], "EQ")
    bk = b4.book_returns(net, b4.SUBSETS[sname], wq)
    bo = b4.apply_overlay(bk.loc[oos.index])
    s = b4.stats(bo)
    print("  %-6s OOS Sh %.2f CAGR %.2f%% DD %.2f%% vol %.1f%%" % (
        sname, s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100, s["vol"] * 100))

print("\n=== 6. Biggest single days (raw CORE3 EQ) — concentration of P&L ===")
big = b_oos.nlargest(5)
print("  top-5 positive days:")
for idx, v in big.items():
    print("     %s  %+7.2f%%" % (idx.date(), v * 100))
print("  top-5 share of total: %.0f%%" % (big.sum() / total * 100))

print("\n=== 7. Correlation regime (crack_321 vs cross_sectional) ===")
print("  IS: %.2f  OOS: %.2f" % (isw[["crack_321", "cross_sectional"]].corr().iloc[0, 1],
                                  oos[["crack_321", "cross_sectional"]].corr().iloc[0, 1]))
print("  OOS corr matrix (CORE3):")
print(oos[b4.SUBSETS["CORE3"]].corr().round(2).to_string())

print("\n=== 8. Overlay: how often de-risked, and what it cost ===")
ob = b4.apply_overlay(b_oos)
print("  raw vol %.1f%%  overlay vol %.1f%%  -> participation %.0f%%" % (
    b4.stats(b_oos)["vol"] * 100, b4.stats(ob)["vol"] * 100,
    b4.stats(ob)["vol"] * 100 / b4.stats(b_oos)["vol"] * 100))

print("\n=== 8b. Overlay capture of the crisis windfall days ===")
print("  raw top-5 days vs overlay same days:")
for idx, v in b_oos.nlargest(5).items():
    print("     %s  raw %+7.2f%%  overlay %+7.2f%%" % (idx.date(), v * 100, ob.loc[idx] * 100))
print("  raw total of top-5: %+.2f%%  overlay total of same days: %+.2f%%" % (
    b_oos.nlargest(5).sum() * 100, ob.loc[b_oos.nlargest(5).index].sum() * 100))
print("  overlay best day: %s %+.2f%%" % (ob.idxmax().date(), ob.max() * 100))

print("\n=== 9. Engine vs overlay on IS (is the overlay IS-consistent?) ===")
b_is = book.loc[isw.index]
print("  IS raw   Sh %.2f DD %.2f%%" % (b4.stats(b_is)["sharpe"], b4.stats(b_is)["maxdd"] * 100))
print("  IS overlay Sh %.2f DD %.2f%%" % (b4.stats(b4.apply_overlay(b_is))["sharpe"],
                                          b4.stats(b4.apply_overlay(b_is))["maxdd"] * 100))