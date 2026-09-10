"""Check zero-crossing artifacts in level pct_change across the full window."""

import importlib.util
import pandas as pd
import numpy as np

spec = importlib.util.spec_from_file_location("fb", "factor_book.py")
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

df = pd.read_parquet("/tmp/panel_adj_2007_2026.parquet").sort_index()
levels = fb.build_levels(df)

print("level min/max over FULL 2007-2026 window:")
for k, s in levels.items():
    print("  %-12s min=%8.3f max=%8.3f  n<=0=%d" % (k, s.min(), s.max(), (s <= 0).sum()))
print()
for k, s in levels.items():
    pc = s.pct_change()
    big = pc.abs().nlargest(3)
    print(k, "largest pct_change days:")
    prev = s.shift(1)
    for idx, v in big.items():
        print("    %s  level_prev=%+.3f  level=%+.3f  pct=%+.1f%%" % (idx.date(), prev.loc[idx], s.loc[idx], v * 100))