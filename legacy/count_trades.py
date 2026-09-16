"""Count discrete trades per factor in the factor book."""

import importlib.util

import pandas as pd
import numpy as np

spec = importlib.util.spec_from_file_location("fb", "/home/sebas/algoterminal-strategy-dev/factor_book.py")
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

df = fb.fetch_panel("2023-09-08", "2026-09-08")
levels = fb.build_levels(df)

factors = {}
factors.update(fb.f1_positions(levels))
factors.update(fb.f2_positions(levels))
factors.update(fb.f3_positions(levels))
factors.update(fb.f4_positions(levels))

def count_trades(pos: pd.Series, since: str = "2024-01-01") -> tuple[int, int, int]:
    p = pos.loc[pos.index >= since].fillna(0.0)
    side = np.sign(p.to_numpy())
    # a new trade starts when side changes from 0/nonzero to a different nonzero
    trades = 0
    prev = 0
    n_days = 0
    for s in side:
        if s != 0:
            n_days += 1
            if prev == 0:
                trades += 1
        prev = s
    return trades, n_days, len(p)

print("=== DISCRETE TRADES PER FACTOR (post-warm-up >= 2024-01-01) ===")
total_trades = 0
total_days = 0
for name, pos in factors.items():
    t, d, n = count_trades(pos)
    total_trades += t
    total_days += d
    print("  %-14s trades=%3d  daysInMarket=%4d  (%.1f%% of %d days)" % (name, t, d, d / n * 100, n))

print()
print("Book (sum across factors): %d distinct entries, %d factor-days in market" % (total_trades, total_days))
# How many calendar days had at least one factor on
any_pos = pd.DataFrame(factors).loc[factors[list(factors)[0]].index >= "2024-01-01"].abs().sum(axis=1) > 0
print("Calendar days with at least one factor on: %d (%.1f%% of trading days)" % (any_pos.sum(), any_pos.mean() * 100))
avg = any_pos.mean()
print("Average number of factors on per active day: %.2f" % (pd.DataFrame(factors).loc[factors[list(factors)[0]].index >= "2024-01-01"].abs().gt(0).sum(axis=1)[any_pos].mean()))
