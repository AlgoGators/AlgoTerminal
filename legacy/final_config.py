"""Final config decision: overlay stickiness variants + CAP interaction."""
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


def apply_overlay_med(book, vol_target=0.10, cut=-0.06, halt=-0.10, reenter=-0.03):
    """Medium-stickiness: OFF->CUT(0.5) once engine dd recovers above reenter,
    CUT->FULL on engine new high. Halt only applies from active states."""
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    for t in range(n):
        scale[t] = state
        r = float(book.iloc[t])
        ret = r * float(g.iloc[t]) * scale[t]
        eq *= 1.0 + ret
        hwm = max(hwm, eq)
        exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        eng_dd = eng_eq / eng_hwm - 1.0
        new_high = eng_eq >= was_hwm
        if state == 1.0:
            if exp_dd <= halt:
                state = 0.0
            elif exp_dd <= cut:
                state = 0.5
        elif state == 0.5:
            if exp_dd <= halt:
                state = 0.0
            elif new_high:
                state = 1.0
            elif eng_dd <= reenter:
                state = 0.0
        else:  # OFF
            if new_high:
                state = 1.0
            elif eng_dd > reenter:
                state = 0.5
    return book * pd.Series(scale, index=book.index) * g


df = pd.read_parquet(b4.PANEL).sort_index()
levels = fb.build_levels(df)

print("=== CORE3 EQ: overlay variants (NOCAP and CAP5) ===")
for capname, cap3 in [("NOCAP", None), ("CAP5", 0.05)]:
    factors, rets, turn = b4.build_v4(levels, cap3)
    net = b4.apply_costs(factors, rets, turnover=turn)
    isw = b4.window(net, b4.IS_START, df.index.max())
    oos = b4.window(net, b4.OOS_START, b4.IS_START)
    w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
    b_is = b4.book_returns(net, b4.SUBSETS["CORE3"], w).loc[isw.index]
    b_oos = b4.book_returns(net, b4.SUBSETS["CORE3"], w).loc[oos.index]
    variants = {
        "raw": lambda s: s,
        "ov_strict": lambda s: b4.apply_overlay(s),
        "ov_med": lambda s: apply_overlay_med(s),
        "ov_loose": lambda s: apply_overlay_med(s, reenter=-0.05),
    }
    print("\n[%s]" % capname)
    for vname, fn in variants.items():
        si, so = b4.stats(fn(b_is)), b4.stats(fn(b_oos))
        flat = int((fn(b_oos).groupby(fn(b_oos).index.year).sum() == 0).sum())
        print("  %-9s | IS Sh %5.2f DD %7.2f%% | OOS Sh %5.2f CAGR %7.2f%% DD %7.2f%% vol %5.1f%% worst %6.2f%% | flatYr %d" % (
            vname, si["sharpe"], si["maxdd"] * 100, so["sharpe"], so["cagr"] * 100,
            so["maxdd"] * 100, so["vol"] * 100, so["worst_day"] * 100, flat))

# strict-vs-med yearly for the recommended config
factors, rets, turn = b4.build_v4(levels, None)
net = b4.apply_costs(factors, rets, turnover=turn)
isw = b4.window(net, b4.IS_START, df.index.max())
oos = b4.window(net, b4.OOS_START, b4.IS_START)
w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
b_oos = b4.book_returns(net, b4.SUBSETS["CORE3"], w).loc[oos.index]
om = apply_overlay_med(b_oos)
os_ = b4.apply_overlay(b_oos)
print("\nYearly (CORE3 EQ NOCAP): raw | med | strict")
for y, g in b_oos.groupby(b_oos.index.year):
    print("  %4d  %+7.2f%%  %+7.2f%%  %+7.2f%%" % (y, g.sum() * 100, om.loc[g.index].sum() * 100,
                                                    os_.loc[g.index].sum() * 100))

print("\n=== final recommendation sweep (CORE3 EQ NOCAP, med overlay) ===")
for cut_, halt_, re_ in [(-0.06, -0.10, -0.03), (-0.05, -0.09, -0.03), (-0.04, -0.08, -0.03),
                         (-0.06, -0.10, -0.02), (-0.05, -0.085, -0.025), (-0.04, -0.075, -0.02)]:
    om2 = apply_overlay_med(b_oos, cut=cut_, halt=halt_, reenter=re_)
    s = b4.stats(om2)
    print("  cut %5.3f halt %5.3f re %5.3f | OOS Sh %5.2f CAGR %7.2f%% DD %7.2f%% vol %5.1f%% worst %6.2f%%" % (
        cut_, halt_, re_, s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100, s["vol"] * 100, s["worst_day"] * 100))

# IS-side for the chosen recommended thresholds
for cut_, halt_, re_ in [(-0.05, -0.085, -0.025)]:
    b_is = b4.book_returns(net, b4.SUBSETS["CORE3"], w).loc[isw.index]
    omi = apply_overlay_med(b_is, cut=cut_, halt=halt_, reenter=re_)
    s = b4.stats(omi)
    print("\nIS-side same thresholds: Sh %5.2f CAGR %7.2f%% DD %7.2f%% vol %5.1f%%" % (
        s["sharpe"], s["cagr"] * 100, s["maxdd"] * 100, s["vol"] * 100))