"""Reversal-speed diagnostics (Round 8, step 1).

Question: does PATH separate the windfall days from the bleed years?
Round 4 the crude-stress gate (CL z <= -1.5) captured the 2020 windfall
but blew DD because 2013/2019 bleeds ALSO sit in stressed states. Round 7
hypothesis: the separator is the INFLECTION, not the level. A V-shaped
crash (fast deepening + fast reversal) pays; a slow grind bleeds.

Everything is causal: state features are known at close t-1 (or earlier).
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
b_is = book.loc[isw.index].copy()

# --- causal path-state features (known at close t-1) ---
cl = df.CL
crude_ret20 = cl.pct_change(20).shift(1)          # 20d crude move ended t-1
crude_ret5 = cl.pct_change(5).shift(1)            # 5d crude move ended t-1
held_depth = depth.shift(1)                        # most-crushed held leg z, t-1
held_depth5 = depth.shift(6)                       # same leg depth 5 days earlier
crash5 = held_depth5 - held_depth                  # deepening speed: >0 = crushed FURTHER in 5d


def state_frame(r: pd.Series, d5) -> pd.DataFrame:
    """Join causal state features to a return series."""
    out = pd.DataFrame({
        "ret": r,
        "ret5": r.rolling(5).sum(),
        "depth": held_depth.reindex(r.index),
        "crash5": d5.reindex(r.index),
        "crude20": crude_ret20.reindex(r.index),
        "crude5": crude_ret5.reindex(r.index),
    })
    out["held"] = (depth.reindex(r.index).notna())
    return out


sf_oos = state_frame(b_oos, crash5)

print("=== A) top OOS raw days: what was the path-state at t-1? ===")
print("  %-12s %8s %8s %8s %8s %8s %8s" % ("date", "ret", "depth", "crash5", "crude20", "crude5", "held?"))
for idx, v in b_oos.nlargest(10).items():
    row = sf_oos.loc[idx]
    print("  %-12s %+7.2f%% %8.2f %8.2f %8.1f%% %8.1f%% %8s" % (
        idx.date(), v * 100, row.depth, row.crash5, row.crude20 * 100, row.crude5 * 100, bool(row.held)))

print("\n=== A2) worst OOS days: same state ===")
for idx, v in b_oos.nsmallest(10).items():
    row = sf_oos.loc[idx]
    print("  %-12s %+7.2f%% %8.2f %8.2f %8.1f%% %8.1f%% %8s" % (
        idx.date(), v * 100, row.depth, row.crash5, row.crude20 * 100, row.crude5 * 100, bool(row.held)))

print("\n=== B) bleed years: 2013 / 2019 / 2014-16 state ===")
for y in [2013, 2014, 2015, 2016, 2019, 2020]:
    g = sf_oos.loc[str(y)]
    print("  %4d  ret %+7.2f%%  n %4d  held%% %5.1f  depth median %6.2f  crash5 median %6.2f  crude20 median %6.1f%%  crude5 median %6.1f%%" % (
        y, g.ret.sum() * 100, len(g), g.held.mean() * 100, g.depth.median(),
        g.crash5.median(), g.crude20.median() * 100, g.crude5.median() * 100))


# --- C) the discriminator: V-state (fast deepening OR crude crash) vs grind ---
# Pre-registered a priori: V = crash5 <= -0.6 OR crude20 <= -15%
def v_state(sf: pd.DataFrame) -> pd.Series:
    return (sf.crash5 <= -0.6) | (sf.crude20 <= -0.15)


print("\n=== C) V-state vs grind on OOS (causal, t-1) ===")
for label, sf in [("OOS", sf_oos), ("IS", state_frame(b_is, crash5))]:
    v = v_state(sf)
    print("  [%s] V-state days: %d / %d (%.1f%%)" % (label, v.sum(), len(v), v.mean() * 100))
    for grp in [True, False]:
        g = sf[v == grp]
        if len(g) == 0:
            continue
        day_ret = g.ret.mean()
        fwd5 = g.ret5.mean()
        big_up = (g.ret > 0.02).mean() * 100
        big_dn = (g.ret < -0.02).mean() * 100
        print("    V=%s  n %4d  mean day %+7.2f%%  mean fwd5 %+7.2f%%  bigUp>2%% %5.1f%%  bigDn<-2%% %5.1f%%" % (
            grp, len(g), day_ret * 100, fwd5 * 100, big_up, big_dn))

# negative control: shuffle returns, keep states fixed (states carry no info)
print("\n=== C2) negative control: shuffle OOS returns, keep V-state fixed ===")
rng = np.random.default_rng(42)
sh_diffs = []
for _ in range(30):
    perm = rng.permutation(len(sf_oos))
    sh = sf_oos.copy()
    sh["ret"] = sf_oos.ret.to_numpy()[perm]
    sh["ret5"] = sh.ret.rolling(5).sum()
    v = v_state(sh)
    d = sh.ret[v].mean() - sh.ret[~v].mean()
    sh_diffs.append(d)
print("  shuffled mean-day diff V-grind: mean %+.4f%%  sd %.4f%%  (real: %+.4f%%)" % (
    np.mean(sh_diffs) * 100, np.std(sh_diffs) * 100,
    (sf_oos.ret[v_state(sf_oos)].mean() - sf_oos.ret[~v_state(sf_oos)].mean()) * 100))

# --- D) windfall capture potential: how much of the big days sit in V-state ---
print("\n=== D) V-state captures the windfalls ===")
top = b_oos.nlargest(20)
print("  top-20 raw days total %+6.2f%%; inside V-state: %+6.2f%% (%d of %d days)" % (
    top.sum() * 100, top[v_state(sf_oos.loc[top.index])].sum() * 100,
    int(v_state(sf_oos.loc[top.index]).sum()), len(top)))
bot = b_oos.nsmallest(20)
print("  worst-20 raw days total %+6.2f%%; inside V-state: %+6.2f%% (%d of %d days)" % (
    bot.sum() * 100, bot[v_state(sf_oos.loc[bot.index])].sum() * 100,
    int(v_state(sf_oos.loc[bot.index]).sum()), len(bot)))
