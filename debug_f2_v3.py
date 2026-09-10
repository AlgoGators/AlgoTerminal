"""Dig into cross_sectional -22.5% on 2012-01-09 under the v3 engine."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
spec = importlib.util.spec_from_file_location("b3", str(DEV / "book_oos_v3.py"))
b3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b3)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

df = b3.load_panel() if hasattr(b3, "load_panel") else pd.read_parquet(b3.PANEL).sort_index()
levels = fb.build_levels(df)
factors, rets = b3.build_v3(levels, None)

pos = factors["cross_sectional"]
r = rets["cross_sectional"]
for d in ["2007-12-20", "2012-01-09"]:
    i = pos.index.get_loc(d)
    print("=== %s ===" % d)
    w = pd.DataFrame({
        "pos": pos.iloc[i - 3:i + 3],
        "ret": (r.iloc[i - 3:i + 3] * 100).round(2),
    })
    print(w.to_string())
    # chosen leg level
    held = b3.chosen_leg_every_day(levels, ["crack_321", "crack_gas", "crack_ho"])
    lvl = levels["crack_321"]
    print("chosen level: %.3f (prev %.3f)" % (held.iloc[i], held.iloc[i - 1]))
    base = b3.base_of(held.fillna(lvl)).shift(1)
    print("base prev: %.3f  dlevel: %.3f  pos_prev: %.3f" % (base.iloc[i], held.iloc[i] - held.iloc[i - 1], pos.iloc[i - 1]))
    print("expected ret: pos_prev * d / base = %.4f" % (pos.iloc[i - 1] * (held.iloc[i] - held.iloc[i - 1]) / base.iloc[i]))
    # but which values did sp_ret use?
    zdf = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in ["crack_321", "crack_gas", "crack_ho"]})
    print("\nz values around:")
    print(zdf.iloc[i - 3:i + 3].round(2).to_string())
    # what are the LEVEL values the day before/after
    print("\nlevels:")
    for k in ["crack_321", "crack_gas", "crack_ho"]:
        print("  %-12s" % k, levels[k].iloc[i - 3:i + 3].round(3).to_dict())