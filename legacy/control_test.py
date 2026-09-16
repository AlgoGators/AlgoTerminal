"""Negative control: overlay on time-shuffled returns must NOT cap DD (else it's luck)."""
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
b_oos = b4.book_returns(net, b4.SUBSETS["CORE3"], w).loc[oos.index]

raw_sh = b4.stats(b_oos)["sharpe"]
raw_dd = b4.stats(b_oos)["maxdd"]
ov_sh = b4.stats(b4.apply_overlay(b_oos))["sharpe"]
ov_dd = b4.stats(b4.apply_overlay(b_oos))["maxdd"]
print("raw   : Sh %.2f DD %.2f%%" % (raw_sh, raw_dd * 100))
print("overlay: Sh %.2f DD %.2f%%" % (ov_sh, ov_dd * 100))

rng = np.random.default_rng(42)
shuffled = []
for trial in range(20):
    perm = rng.permutation(len(b_oos))
    s = pd.Series(b_oos.to_numpy()[perm], index=b_oos.index)
    so = b4.apply_overlay(s)
    shuffled.append((b4.stats(so)["sharpe"], b4.stats(so)["maxdd"]))
sh0 = np.array([x[0] for x in shuffled])
dd0 = np.array([x[1] for x in shuffled])
print("\nshuffled (20 trials): overlay Sharpe mean %.2f (raw %.2f); MaxDD mean %.2f%%" % (
    sh0.mean(), raw_sh, dd0.mean() * 100))
print("shuffled Sharpe vs raw: %d/%d trials better" % ((sh0 > raw_sh).sum(), len(sh0)))
print("shuffled MaxDD vs overlay: any trial as good as %.2f%%? %s" % (
    ov_dd * 100, "YES" if bool((dd0 <= ov_dd).any()) else "NO"))

# negative control 2: overlay on constant vol / iid noise
noise = pd.Series(rng.normal(b_oos.mean(), b_oos.std(), len(b_oos)), index=b_oos.index)
so_noise = b4.apply_overlay(noise)
print("\niid-noise overlay: Sh %.2f DD %.2f%% (raw Sh %.2f DD %.2f%%)" % (
    b4.stats(so_noise)["sharpe"], b4.stats(so_noise)["maxdd"] * 100,
    b4.stats(noise)["sharpe"], b4.stats(noise)["maxdd"] * 100))