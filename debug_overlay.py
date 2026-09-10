"""Debug overlay trough for CORE3 HLV OOS."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
spec = importlib.util.spec_from_file_location("b2", str(DEV / "book_oos_v2.py"))
b2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b2)
spec2 = importlib.util.spec_from_file_location("lb", str(DEV / "long_backtest.py"))
lb = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(lb)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

df = b2.load_panel()
levels = fb.build_levels(df)
positions, rets = lb.build_positions_and_returns(levels)
net = lb.apply_costs(positions, rets, 5.0, 20.0)
isw = b2.window(net, b2.IS_START, df.index.max())
oos = b2.window(net, b2.OOS_START, b2.IS_START)
factors = b2.SUBSETS["CORE3"]
w = b2.weight_scheme(isw[factors], "HLV")
book = b2.book_returns(net, factors, w)
b_oos = book.loc[oos.index]
ob = b2.apply_overlay(b_oos)
eq = (1 + ob).cumprod()
dd = eq / eq.cummax() - 1
trough = dd.idxmin()
print("overlay trough:", trough.date(), "dd=%.2f%%" % (dd.min() * 100))

rv = b_oos.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
gear = (0.10 / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
dd_eng = b2.drawdown(b_oos)

# Rebuild the policy path to inspect state at trough
ddp = dd_eng.shift(1).to_numpy(dtype=float)
state = 1.0
pol = np.zeros(len(b_oos))
states = []
for i in range(len(b_oos)):
    if np.isnan(ddp[i]):
        pol[i] = state
        continue
    d = ddp[i]
    if state == 1.0:
        if d <= -0.075:
            state = 0.5
    elif state == 0.5:
        if d <= -0.10:
            state = 0.0
        elif d > -0.04:
            state = 1.0
    else:
        if d > -0.04:
            state = 1.0
    pol[i] = state

print("engine trough:", dd_eng.idxmin().date(), "dd=%.2f%%" % (dd_eng.min() * 100))
print("policy at overlay trough:", pol[list(b_oos.index).index(trough)])
print("engine dd at overlay trough: %.2f%%" % (dd_eng.loc[trough] * 100))
print("gear at trough: %.3f" % gear.loc[trough])

# scan for policy==1 days with large negative overlay returns
tbl = pd.DataFrame({"eng": b_oos, "ov": ob, "pol": pol, "gear": gear.to_numpy(), "ddeng": dd_eng})
tbl.index = b_oos.index
worst_ov = tbl.nsmallest(10, "ov")
print("\nworst overlay days:")
for idx, row in worst_ov.iterrows():
    print("  %s  ov %+7.2f%%  eng %+7.2f%%  pol %.2f  gear %.2f  ddeng %+6.2f%%" % (
        idx.date(), row.ov * 100, row.eng * 100, row.pol, row.gear, row.ddeng * 100))

print("\nlarge eng days when pol==1 (full exposure):")
full = tbl[tbl.pol == 1.0]
big = full[full.eng.abs() > 0.02]
print(big[["ov", "eng", "ddeng"]].to_string())