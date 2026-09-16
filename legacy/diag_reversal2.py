"""Reversal-speed diagnostics (Round 8, step 2): correct-sign bucket analysis.

crash5 = depth(t-6) - depth(t-1). POSITIVE = the held leg deepened fast
in the last 5 days (fast crash INTO the position). Negative = shallowing.
Bleed years (2013/2019) sit DEEP but with crash5 ~ 0 (grind, not crash).
Hypothesis: the fast-deepening state is where the windfall lives.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
spec = importlib.util.spec_from_file_location("b5", str(DEV / "book_oos_v5.py"))
b5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b5)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

df = pd.read_parquet(b5.PANEL).sort_index()
levels = fb.build_levels(df)
levels["__df__"] = df

factors, rets, turn, legpos = b5.build_v5(levels, None, False)
net = b5.apply_costs(factors, rets, turnover=turn)
isw = b5.window(net, b5.IS_START, df.index.max())
oos = b5.window(net, b5.OOS_START, b5.IS_START)

zdf = {}
for leg in ["crack_321", "crack_gas", "crack_ho", "ng", "bzwti"]:
    zdf[leg] = fb.seasonal_z(levels[leg])
for leg in ["brent321", "brent_gas", "brent_ho"]:
    zdf[leg] = fb.seasonal_z(b5.brent_levels(df)[leg])
depth = b5.book_depth(legpos, zdf, net.index)

w = b5.weight_scheme(isw[b5.SUBSETS["CORE3"]], "EQ")
book = b5.book_returns(net, b5.SUBSETS["CORE3"], w)
b_oos = book.loc[oos.index].copy()

cl = df.CL
crude_ret20 = cl.pct_change(20).shift(1)
crude_ret5 = cl.pct_change(5).shift(1)
held_depth = depth.shift(1)
held_depth5 = depth.shift(6)
crash5 = held_depth5 - held_depth


def sf(r):
    return pd.DataFrame({
        "ret": r, "ret5": r.rolling(5).sum(),
        "depth": held_depth.reindex(r.index),
        "crash5": crash5.reindex(r.index),
        "crude20": crude_ret20.reindex(r.index),
    })


s = sf(b_oos)
mask = s.depth.notna() & s.crash5.notna()
g = s[mask]

print("=== crash5 buckets (OOS, held days only) ===")
bins = [(-np.inf, -1.0), (-1.0, -0.2), (-0.2, 0.2), (0.2, 1.0), (1.0, np.inf)]
print("  %-14s %5s %10s %10s %8s %8s %8s %10s" % ("bucket", "n", "mean_day", "mean_fwd5", "bigUp>2", "bigDn<-2", "med_d", "top5sh"))
for lo, hi in bins:
    b = g[(g.crash5 > lo) & (g.crash5 <= hi)]
    if len(b) == 0:
        continue
    top5 = b.ret.nlargest(5).sum()
    print("  %6.1f..%+5.1f %5d %+10.3f%% %+10.3f%% %7.1f%% %7.1f%% %8.2f %+9.2f%%" % (
        lo, hi, len(b), b.ret.mean() * 100, b.ret5.mean() * 100,
        (b.ret > 0.02).mean() * 100, (b.ret < -0.02).mean() * 100,
        b.depth.median(), top5 * 100))

print("\n=== crude20 buckets (OOS, held days only) ===")
cbins = [(-np.inf, -0.15), (-0.15, -0.05), (-0.05, 0.05), (0.05, 0.15), (0.15, np.inf)]
print("  %-14s %5s %10s %10s %8s %8s %10s" % ("bucket", "n", "mean_day", "mean_fwd5", "bigUp>2", "bigDn<-2", "top5sh"))
for lo, hi in cbins:
    b = g[(g.crude20 > lo) & (g.crude20 <= hi)]
    if len(b) == 0:
        continue
    top5 = b.ret.nlargest(5).sum()
    print("  %6.1f..%+5.1f %5d %+10.3f%% %+10.3f%% %7.1f%% %7.1f%% %+9.2f%%" % (
        lo * 100, hi * 100, len(b), b.ret.mean() * 100, b.ret5.mean() * 100,
        (b.ret > 0.02).mean() * 100, (b.ret < -0.02).mean() * 100, top5 * 100))

print("\n=== fast-deepening days (crash5 >= 1.0): what are they? ===")
fd = g[g.crash5 >= 1.0]
print("  n=%d (%.1f%% of held days)" % (len(fd), len(fd) / len(g) * 100))
print("  total ret %+6.2f%%   mean %+6.3f%%  bigUp %5.1f%%  bigDn %5.1f%%" % (
    fd.ret.sum() * 100, fd.ret.mean() * 100, (fd.ret > 0.02).mean() * 100,
    (fd.ret < -0.02).mean() * 100))
print("  by year:")
for y, b in fd.groupby(fd.index.year):
    print("    %4d  n %3d  ret %+7.2f%%" % (y, len(b), b.ret.sum() * 100))
print("\n  biggest fast-deep days:")
for idx, v in fd.ret.nlargest(8).items():
    r = g.loc[idx]
    print("    %-12s %+6.2f%%  crash5 %+5.2f  depth %6.2f  crude20 %6.1f%%" % (
        idx.date(), v * 100, r.crash5, r.depth, r.crude20 * 100))
print("  worst fast-deep days:")
for idx, v in fd.ret.nsmallest(8).items():
    r = g.loc[idx]
    print("    %-12s %+6.2f%%  crash5 %+5.2f  depth %6.2f  crude20 %6.1f%%" % (
        idx.date(), v * 100, r.crash5, r.depth, r.crude20 * 100))

# interaction: fast-deep AND deep (V-crash) vs fast-deep from shallow
print("\n=== fast-deep x depth interplay ===")
for dlo, dhi, dlab in [(-np.inf, -1.5, "deep<=-1.5"), (-1.5, 0, "mid"), (0, np.inf, "shallow")]:
    b = g[(g.crash5 >= 1.0) & (g.depth > dlo) & (g.depth <= dhi)]
    if len(b):
        print("  %-12s n %4d  mean %+6.3f%%  total %+7.2f%%  bigUp %5.1f%%  bigDn %5.1f%%" % (
            dlab, len(b), b.ret.mean() * 100, b.ret.sum() * 100,
            (b.ret > 0.02).mean() * 100, (b.ret < -0.02).mean() * 100))
