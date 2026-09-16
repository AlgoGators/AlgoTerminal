"""Reversal-speed discriminator: confirm V-state fact with shuffled control."""

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

held_depth = depth.shift(1)
crash5 = depth.shift(6) - depth.shift(1)

def v_state(idx, thr_crash=1.0, thr_depth=-1.25):
    d = held_depth.reindex(idx)
    c = crash5.reindex(idx)
    return (c >= thr_crash) & (d <= thr_depth)

sf_oos = pd.DataFrame({"ret": b_oos, "d": held_depth.reindex(b_oos.index), "c": crash5.reindex(b_oos.index)})
sf_is = pd.DataFrame({"ret": b_is, "d": held_depth.reindex(b_is.index), "c": crash5.reindex(b_is.index)})

for thr_crash, thr_depth in [(1.0, -1.25), (1.0, -1.5), (0.8, -1.25)]:
    v_oos = v_state(b_oos.index, thr_crash, thr_depth)
    v_is = v_state(b_is.index, thr_crash, thr_depth)
    print(f"\n=== V = crash5 >= {thr_crash} & depth <= {thr_depth} ===")
    for label, v, sf in [("OOS", v_oos, sf_oos), ("IS", v_is, sf_is)]:
        n = int(v.sum())
        tot = len(v)
        mv = sf.ret[v].mean() * 100 if n else float("nan")
        mf = sf.ret[~v].mean() * 100 if (tot - n) else float("nan")
        # shuffle control: 500 shuffles of V labels within held days
        rng = np.random.default_rng(0)
        # restrict to held days
        held = sf.d.notna()
        v_held = v[held]
        ret_held = sf.ret[held]
        diff_real = ret_held[v_held].mean() - ret_held[~v_held].mean()
        diffs = []
        for _ in range(500):
            perm = rng.permutation(len(ret_held))
            sh_v = v_held.to_numpy()[perm]
            # keep same count
            d = ret_held.to_numpy()[sh_v].mean() - ret_held.to_numpy()[~sh_v].mean() if sh_v.sum() and (~sh_v).sum() else 0.0
            diffs.append(d)
        diffs = np.array(diffs)
        p = (np.abs(diffs) >= abs(diff_real)).mean()
        print(f"  {label} V {n}/{tot} ({n/tot*100:.1f}%)  mean V {mv:+.4f}%  grind {mf:+.4f}%  diff {diff_real*100:+.4f}%  shuffle sd {diffs.std()*100:.4f}%  p~{p:.3f}")
        # count of top days inside V
        top = sf.ret.nlargest(20)
        print(f"    top-20 total {top.sum()*100:+.2f}% inside V {top[v.reindex(top.index).fillna(False)].sum()*100:+.2f}% ({int(v.reindex(top.index).fillna(False).sum())}/20)")
