"""Diagnose V3 failure (depth by year) + test crude-stress gate (exploratory, one pass)."""
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

# depth by year
zdf = {}
for leg in ["crack_321", "crack_gas", "crack_ho", "ng", "bzwti"]:
    zdf[leg] = fb.seasonal_z(levels[leg])
for leg in ["brent321", "brent_gas", "brent_ho"]:
    zdf[leg] = fb.seasonal_z(b5.brent_levels(df)[leg])
depth = b5.book_depth(legpos, zdf, net.index)
print("=== depth (most-crushed held leg z) by year: % of days <= -1.25 ===")
for y in [2013, 2014, 2016, 2019, 2020, 2024]:
    g = depth.loc[str(y)]
    print("  %4d  days<=-1.25: %5.1f%%   min %.2f" % (y, (g <= -1.25).mean() * 100, g.min()))

# crude stress series: deseasonalized z of CL (same seasonal_z machinery)
clz = fb.seasonal_z(df.CL)
print("\n=== CL seasonal z by year: % of days <= -1.5 ===")
for y in [2013, 2019, 2020, 2022, 2024]:
    g = clz.loc[str(y)]
    print("  %4d  days<=-1.5: %5.1f%%   min %.2f" % (y, (g <= -1.5).mean() * 100, g.min()))


def overlay_gate(book, gate, vol_target=0.10, cut=-0.06, halt=-0.10):
    """V2 ladder + gate series forces FULL when gate<=thr (gate through t-1)."""
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    gv = gate.reindex(book.index).to_numpy(dtype=float)
    for t in range(n):
        scale[t] = state
        r = float(book.iloc[t])
        ret = r * float(g.iloc[t]) * scale[t]
        eq *= 1.0 + ret
        hwm = max(hwm, eq)
        exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        new_high = eng_eq >= was_hwm
        if not np.isnan(gv[t]) and gv[t] <= -1.5:
            state = 1.0
        elif state == 1.0:
            if exp_dd <= halt:
                state = 0.0
            elif exp_dd <= cut:
                state = 0.5
        elif state == 0.5:
            if exp_dd <= halt:
                state = 0.0
            elif new_high:
                state = 1.0
        else:
            if new_high:
                state = 1.0
    return book * pd.Series(scale, index=book.index) * g


w = b5.weight_scheme(isw[b5.SUBSETS["CORE3"]], "EQ")
book = b5.book_returns(net, b5.SUBSETS["CORE3"], w)
b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
clz_is, clz_oos = clz.loc[isw.index], clz.loc[oos.index]

print("\n=== CORE3 EQ: V2 vs crude-stress gate (CL z <= -1.5) ===")
for label, fn in [("V2", lambda s: b5.apply_overlay_v2(s)),
                  ("CLGATE", lambda s: overlay_gate(s, clz.loc[s.index]))]:
    si, so = b5.stats(fn(b_is)), b5.stats(fn(b_oos))
    print("  %-7s | IS Sh %5.2f DD %7.2f%% | OOS Sh %5.2f CAGR %7.2f%% DD %7.2f%% vol %5.1f%% worst %6.2f%%" % (
        label, si["sharpe"], si["maxdd"] * 100, so["sharpe"], so["cagr"] * 100,
        so["maxdd"] * 100, so["vol"] * 100, so["worst_day"] * 100))

# top-5 day capture for both
for label, fn in [("V2", lambda s: b5.apply_overlay_v2(s)), ("CLGATE", lambda s: overlay_gate(s, clz.loc[s.index]))]:
    ob = fn(b_oos)
    top5 = b_oos.nlargest(5)
    cap = ob.loc[top5.index].sum()
    print("  %-7s top-5 day capture: %+.2f%% of raw %+.2f%%" % (label, cap * 100, top5.sum() * 100))
    print("    2020-04-20: raw %+.2f%% overlay %+.2f%%" % (b_oos.loc["2020-04-20"] * 100, ob.loc["2020-04-20"] * 100))

# negative control: shuffle for CLGATE
rng = np.random.default_rng(7)
sh = []
for _ in range(15):
    perm = rng.permutation(len(b_oos))
    s = pd.Series(b_oos.to_numpy()[perm], index=b_oos.index)
    so = overlay_gate(s, clz.loc[s.index])
    sh.append(b5.stats(so)["sharpe"])
print("\n  CLGATE shuffled (15): mean Sharpe %.2f (raw %.2f, V2 %.2f)" % (
    np.mean(sh), b5.stats(b_oos)["sharpe"], b5.stats(b5.apply_overlay_v2(b_oos))["sharpe"]))