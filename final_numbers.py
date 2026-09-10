"""Final summary numbers + trade counts for the report."""
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
        if s != 0 and prev == 0:
            tr += 1
        if s != 0:
            prev = s
    return tr


df = pd.read_parquet(b4.PANEL).sort_index()
levels = fb.build_levels(df)
factors, rets, turn = b4.build_v4(levels, None)
net = b4.apply_costs(factors, rets, turnover=turn)
isw = b4.window(net, b4.IS_START, df.index.max())
oos = b4.window(net, b4.OOS_START, b4.IS_START)

print("=== per-factor v4 corrected, net (5bps/20roll) ===")
print("  %-16s | IS Sh %6s | OOS Sh %6s OOS DD %8s OOS vol %6s OOS trades" % (
    "factor", "Sharpe", "Sharpe", "MaxDD", "vol"))
for f in net.columns:
    si, so = b4.stats(isw[f]), b4.stats(oos[f])
    tr = count_trades(factors[f].loc[oos.index])
    print("  %-16s | %6.2f | %6.2f %8.2f%% %6.1f%% %5d" % (
        f, si["sharpe"], so["sharpe"], so["maxdd"] * 100, so["vol"] * 100, tr))

w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
book = b4.book_returns(net, b4.SUBSETS["CORE3"], w)
b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
ob_is, ob_oos = b4.apply_overlay(b_is), b4.apply_overlay(b_oos)
print("\n=== CORE3 EQ NOCAP ===")
for label, s in [("IS raw", b_is), ("IS overlay", ob_is), ("OOS raw", b_oos), ("OOS overlay", ob_oos)]:
    st = b4.stats(s)
    print("  %-12s CAGR %7.2f%% Sh %5.2f DD %7.2f%% vol %5.1f%% worst %6.2f%%" % (
        label, st["cagr"] * 100, st["sharpe"], st["maxdd"] * 100, st["vol"] * 100, st["worst_day"] * 100))

# old baseline for comparison (from LONG_BACKTEST_FINDINGS): frozen inverse-vol FULL
factors_full, rets_full, turn_full = b4.build_v4(levels, None)
# sim OLD: FULL subset with inverse-vol on IS, no shared fix? old numbers are already recorded; just print for context
print("\n=== baseline (recorded in LONG_BACKTEST_FINDINGS, OLD pipeline) ===")
print("  FULL 5-factor, IS-frozen inverse-vol weights, old F2 basis, no overlay")
print("  OOS: Sh 0.46 CAGR 4.0% DD -21.9% vol 9.5%")
print("  IS : Sh 1.69 (honest) / 2.63 (recorded)")

# worst overlay days and 2013/2019 attribution
print("\nOOS overlay worst days:")
for idx, v in ob_oos.nsmallest(6).items():
    print("  %s  %+7.2f%%" % (idx.date(), v * 100))
print("\n2013 OOS (v4 corrected, per-factor net):")
for f in net.columns:
    print("  %-16s %+8.2f%%" % (f, net[f].loc["2013"].sum() * 100))
print("\n2019 OOS (v4 corrected, per-factor net):")
for f in net.columns:
    print("  %-16s %+8.2f%%" % (f, net[f].loc["2019"].sum() * 100))