"""Check for roll artifacts: raw closes + reconstructed levels around suspect days."""
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

for d in ["2012-01-09", "2019-09-03"]:
    print("=== %s ===" % d)
    idx = df.index.get_loc(d)
    sl = df.iloc[idx - 3: idx + 4]
    print("  panel closes (CL BZ RB HO NG):")
    print(sl.round(3).to_string())
    print("\n  daily % moves of panel:")
    print((sl.pct_change() * 100).round(3).to_string())
    # cross_sectional position & returns
    # rebuild positions with a visible index
pos, rets = lb.build_positions_and_returns(levels)
net = lb.apply_costs(pos, rets, 5.0, 20.0)
for d in ["2012-01-09", "2019-09-03", "2008-12-19"]:
    print("\n=== %s net/pos window ===" % d)
    idx = net.index.get_loc(d)
    w = net.iloc[idx - 3: idx + 2]
    pw = pd.DataFrame({k: v.iloc[idx - 3: idx + 2] for k, v in pos.items()})
    print("net:")
    print(w.round(4).to_string())
    print("positions:")
    print(pw.round(3).to_string())

# Find all days where any single factor net return < -6% (positions at full)
print("\n=== All single-factor days below -6%% (2007-2026) ===")
for f in net.columns:
    s = net[f][net[f] < -0.06]
    if len(s):
        print("%-16s n=%d" % (f, len(s)))
        for idx, v in s.nsmallest(5).items():
            print("   %s  %+7.2f%%" % (idx.date(), v * 100))
        if len(s) > 5:
            print("   ... first + last dates:", s.index[0].date(), "->", s.index[-1].date())
# also count big same-direction moves in the raw levels that can't be market moves
print("\n=== Level daily moves > 15% (rel to base) per level ===")
for name, lvl in levels.items():
    base = lvl.abs().rolling(20, min_periods=10).mean().shift(1)
    rel = (lvl - lvl.shift(1)) / base
    hits = rel[rel.abs() > 0.15].dropna()
    print("%-12s n=%d" % (name, len(hits)))
    for idx, v in hits.nsmallest(4).items():
        print("   %s  %+7.1f%%" % (idx.date(), v * 100))