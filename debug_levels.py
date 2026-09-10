"""Check raw level moves on the worst factor days."""
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

# base = rolling mean |level| over 20
for d in ["2012-01-09", "2019-09-03", "2008-12-19", "2013-04-03"]:
    print("=== %s ===" % d)
    for name, lvl in levels.items():
        l = lvl.loc[d]
        lp = lvl.shift(1).loc[d]
        base = lvl.abs().rolling(20, min_periods=10).mean().shift(1).loc[d]
        rel = (l - lp) / base if base and base != base is False else np.nan
        print("  %-12s level %9.3f prev %9.3f base %9.3f dLevel %9.3f rel %+8.2f%%" % (
            name, l if pd.notna(l) else np.nan, lp if pd.notna(lp) else np.nan,
            base if pd.notna(base) else np.nan,
            (l - lp) if pd.notna(l) and pd.notna(lp) else np.nan,
            rel * 100 if pd.notna(rel) else np.nan))

# which leg did cross_sectional hold on 2012-01-09?
print("\ncross_sectional position and held leg on 2012-01-09:")
positions, rets = lb.build_positions_and_returns(levels)
pos = positions["cross_sectional"].loc["2012-01-09"]
print("  cross_sectional pos:", pos)
for name in ["crack_321", "crack_gas", "crack_ho"]:
    z = fb.seasonal_z(levels[name])
    print("  %-12s z = %.3f" % (name, z.loc["2012-01-09"]))

# big moves in the levels around that date
print("\nlevel moves around 2012-01-09 (5 days):")
for name in ["crack_321", "crack_gas", "crack_ho", "bzwti"]:
    lvl = levels[name]
    s = lvl.loc["2012-01-03":"2012-01-13"]
    print("  %-12s" % name, s.round(2).to_dict())