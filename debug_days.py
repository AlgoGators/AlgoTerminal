"""Diagnose which factors caused the worst CORE3 engine days."""
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

days = ["2012-01-09", "2019-09-03", "2013-04-03", "2008-12-19", "2010-02-10", "2015-10-02"]
print("per-factor net returns on worst CORE3 engine days:")
for d in days:
    print("\n%s:" % d)
    for f in factors:
        print("   %-16s %+8.3f%%" % (f, net[f].loc[d] * 100))
    print("   %-16s %+8.3f%%" % ("BOOK", b_oos.loc[d] * 100))

# correlation of factors over full OOS vs IS
print("\nOOS corr (CORE3):")
print(oos[factors].corr().round(2).to_string())
print("\nIS corr (CORE3):")
print(isw[factors].corr().round(2).to_string())

# how much of the 2013 OOS loss comes from each factor (weighted contributions)
y13 = oos.loc["2013"]
print("\n2013 weighted contributions (CORE3 HLV weights):")
for f in factors:
    print("   %-16s weight %.3f net %+7.2f%% contrib %+7.2f%%" % (f, w[f], y13[f].sum() * 100, w[f] * y13[f].sum() * 100))