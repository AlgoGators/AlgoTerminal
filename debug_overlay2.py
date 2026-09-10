"""Trace overlay equity path 2011-2014."""
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

# Recompute overlay with policy trace, keeping equity path
rv = b_oos.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
gear = (0.10 / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
dd_eng = b2.drawdown(b_oos)
ddp = dd_eng.shift(1).to_numpy(dtype=float)
state = 1.0
pol = np.zeros(len(b_oos))
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

scale_all = pd.Series(gear.to_numpy() * pol, index=b_oos.index).shift(1).fillna(1.0)
ob = b_oos * scale_all
eq = (1 + ob).cumprod()
dd = eq / eq.cummax() - 1

# print monthly 2011-2014
tbl = pd.DataFrame({"eng": b_oos, "ov": ob, "pol": pol, "gear": gear.to_numpy(),
                    "scale": scale_all.to_numpy(), "eq": eq, "dd": dd,
                    "ddeng": dd_eng}).loc["2011-01-01":"2014-12-31"]
tbl["m"] = tbl.index.to_period("M")
m = tbl.groupby("m").agg(eng=("eng", "sum"), ov=("ov", "sum"), pol=("pol", "mean"),
                         gear=("gear", "mean"), eq_end=("eq", "last"),
                         dd_end=("dd", "last"), ddeng_end=("ddeng", "last"))
print(m.round(4).to_string())
print("\nOverlay equity at end 2011: %.3f" % eq.loc["2011-12-30"])
print("Overlay cummax at end 2011: %.3f" % eq.loc[: "2011-12-30"].cummax().iloc[-1])
print("Overlay equity at trough   : %.3f" % eq.loc["2013-04-05"])
print("Overlay cummax before trough: %.3f" % eq.loc[: "2013-04-05"].cummax().iloc[-2])