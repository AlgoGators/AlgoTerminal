"""Inflection diagnostics: 10-day V shape (deepening 10->5 then shallowing 5->0)."""
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

# causal features at day t (known at close t-1)
held = depth.shift(1)                     # depth at t-1
held6 = depth.shift(6)                    # depth at t-6
held11 = depth.shift(11)                  # depth at t-11
prevDeep = held11 - held6                 # >0 = deepened 10->5 days ago
nowShallow = held6 - held                # <0 = shallowed last 5 days (reversal)
crash5 = held6 - held                     # alias for nowShallow with opposite sign? actually same as nowShallow
# also: valley depth = held6 (the bottom)
cl = df.CL
crude20_6 = cl.pct_change(20).shift(6)   # crude 20d ending at t-6
crude5_now = cl.pct_change(5).shift(1)   # crude last 5d ending at t-1

def frame(r):
    return pd.DataFrame({
        "ret": r,
        "ret5": r.rolling(5).sum(),
        "held": held.reindex(r.index),
        "held6": held6.reindex(r.index),
        "prevDeep": prevDeep.reindex(r.index),
        "nowShallow": nowShallow.reindex(r.index),
        "crude20_6": crude20_6.reindex(r.index),
        "crude5": crude5_now.reindex(r.index),
    })

sf_oos = frame(b_oos)
sf_is = frame(b_is)

# top days: what was shape?
print("=== top OOS days shape ===")
for idx, v in b_oos.nlargest(10).items():
    row = sf_oos.loc[idx]
    print(f"{idx.date()} {v*100:+6.2f}%  prevDeep {row.prevDeep:+5.2f} nowShallow {row.nowShallow:+5.2f} held6 {row.held6:+5.2f} held {row.held:+5.2f} crude20_6 {row.crude20_6*100:+6.1f}% crude5 {row.crude5*100:+6.1f}%")

print("\n=== worst OOS days shape ===")
for idx, v in b_oos.nsmallest(10).items():
    row = sf_oos.loc[idx]
    print(f"{idx.date()} {v*100:+6.2f}%  prevDeep {row.prevDeep:+5.2f} nowShallow {row.nowShallow:+5.2f} held6 {row.held6:+5.2f} held {row.held:+5.2f}")

# bucket scan for V-shape: thresholds on prevDeep and nowShallow
print("\n=== V-shape buckets OOS (held days only) ===")
mask = sf_oos.held.notna() & sf_oos.held6.notna() & sf_oos.prevDeep.notna() & sf_oos.nowShallow.notna()
g = sf_oos[mask]
for pd_thr in [0.8, 1.0, 1.2]:
    for ns_thr in [-0.8, -1.0, -1.2]:
        for d_thr in [-1.25, -1.5]:
            v = (g.prevDeep >= pd_thr) & (g.nowShallow <= ns_thr) & (g.held6 <= d_thr)
            n = int(v.sum())
            if n < 15:
                continue
            mv = g.ret[v].mean()*100
            mf = g.ret[~v].mean()*100
            bigUp = (g.ret[v] > 0.02).mean()*100
            bigDn = (g.ret[v] < -0.02).mean()*100
            print(f"prev>={pd_thr:.1f} now<={ns_thr:.1f} held6<={d_thr:.2f}  n={n:4d} ({n/len(g)*100:4.1f}%)  meanV {mv:+6.3f}% vs {mf:+6.3f}%  bigUp {bigUp:4.1f}% bigDn {bigDn:4.1f}%  total {g.ret[v].sum()*100:+7.2f}%")

# also single-side buckets
print("\n=== single-side: nowShallow <= -1.0 (reversal) OOS held ===")
for thr in [-0.5, -0.8, -1.0, -1.2]:
    v = g.nowShallow <= thr
    print(f"nowShallow<={thr:+.1f} n={(v.sum())} mean {g.ret[v].mean()*100:+6.3f}% vs {(g.ret[~v].mean()*100):+6.3f}%")
print("\n=== single-side: prevDeep >= 1.0 (prior deepening) OOS held ===")
for thr in [0.8, 1.0, 1.2]:
    v = g.prevDeep >= thr
    print(f"prevDeep>={thr:.1f} n={(v.sum())} mean {g.ret[v].mean()*100:+6.3f}% vs {(g.ret[~v].mean()*100):+6.3f}%")

# bleed year state for V
print("\n=== V-shape frequency by year OOS (prev>=1.0 now<=-1.0 held6<=-1.25) ===")
v = (g.prevDeep >= 1.0) & (g.nowShallow <= -1.0) & (g.held6 <= -1.25)
for y in sorted(set(g.index.year)):
    gy = g.loc[str(y)]
    vy = v.loc[str(y)]
    print(f"{y} nV={(vy.sum())}/{len(gy)} ({vy.mean()*100:5.2f}%)  retV {gy.ret[vy].sum()*100:+7.2f}%  retAll {gy.ret.sum()*100:+7.2f}%")

# IS check for primary thresholds
print("\n=== IS check (same thresholds, held days) ===")
mask_is = sf_is.held.notna() & sf_is.held6.notna() & sf_is.prevDeep.notna() & sf_is.nowShallow.notna()
gi = sf_is[mask_is]
for pd_thr, ns_thr, d_thr in [(1.0, -1.0, -1.25), (1.2, -1.0, -1.25), (1.0, -1.0, -1.5)]:
    v = (gi.prevDeep >= pd_thr) & (gi.nowShallow <= ns_thr) & (gi.held6 <= d_thr)
    n = int(v.sum())
    mv = gi.ret[v].mean()*100 if n else float("nan")
    mf = gi.ret[~v].mean()*100
    print(f"prev>={pd_thr} now<={ns_thr} d<={d_thr} IS n={n} meanV {mv:+6.3f}% vs {mf:+6.3f}%")
