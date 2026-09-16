"""Phase 3 per-leg attribution for T1 (utilization) and T2-flip (demand).

Reads legs built by the phase3 machinery. Leg-level raw stats only;
the overlay is book-level.
"""
from __future__ import annotations

import importlib.util
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ENGINE = ROOT / "engine"
PANEL = ENGINE / "panel_v2.parquet"
EIA = ENGINE / "eia"

import phase3_harness as p3  # noqa: E402

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)


def single_leg_stats(pos, ret, turn, idx):
    net = b4.apply_costs({0: pos}, {0: ret}, turnover={0: turn})
    s = b4.stats(net[0].loc[idx.intersection(net.index)])
    return s


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    isw_idx = b4.window(pd.DataFrame(index=full_idx), b4.IS_START, full_idx.max()).index
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index

    util_z_d = p3.daily_state(p3.same_month_z(p3.read_series("WPULEUS3").diff()), full_idx)
    gas = p3.read_series("WGTSTUS1")
    dist = p3.read_series("WDISTUS1")
    prod_draw_d = p3.daily_state(-p3.same_month_z((gas + dist).diff()), full_idx)

    def t1(t=False):
        z = util_z_d if not t else -util_z_d
        return pd.Series(np.select([z <= -1.0, z >= 1.0], [1.25, 0.75], default=1.0),
                         index=full_idx)

    def t2(t=False):
        z = prod_draw_d if not t else -prod_draw_d
        return pd.Series(np.select([z >= 1.0, z <= -1.0], [1.25, 0.75], default=1.0),
                         index=full_idx)

    default_tilt = pd.Series(1.0, index=full_idx)
    crack_s = p3.crack_sig(levels["crack_321"])
    f4_s = p3.f4_sig(levels["bzwti"])
    p3.levels = levels
    p3.crack_s = crack_s
    p3.f4_s = f4_s

    rows = []
    print(f"{'leg':<24} {'tilt':<6} {'IS Sh':>7} {'OOS Sh':>7} {'OOS CAGR':>8} {'OOS DD':>8} {'OOS vol':>7}")
    for label, c_t, x_t in [("A", default_tilt, default_tilt),
                            ("T1", t1(), t1()),
                            ("T2flip", t2(True), t2(True))]:
        cpos, cret, cturn = p3.build_tilted_leg(levels["crack_321"], crack_s, c_t,
                                                fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"])
        xpos, xret, xturn = p3.cross_tilted(levels, x_t, fb.VT_F2)
        bpos, bret, bturn = p3.build_tilted_leg(levels["bzwti"], f4_s, default_tilt,
                                                fb.VT_F4, fb.TRAILING_STOP_ON["bzwti"])
        for name, (p, r, t) in {"crack_321": (cpos, cret, cturn),
                                "cross": (xpos, xret, xturn),
                                "bzwti": (bpos, bret, bturn)}.items():
            si = single_leg_stats(p, r, t, isw_idx)
            so = single_leg_stats(p, r, t, oos_idx)
            rows.append({"leg": name, "tilt": label, "IS_sh": si["sharpe"],
                         "OOS_sh": so["sharpe"], "OOS_cagr": so["cagr"],
                         "OOS_dd": so["maxdd"], "OOS_vol": so["vol"]})
            print(f"{name:<24} {label:<6} {si['sharpe']:7.2f} {so['sharpe']:7.2f} "
                  f"{so['cagr']*100:7.2f}% {so['maxdd']*100:7.2f}% {so['vol']*100:6.1f}%")

    # year detail for T1 vs A (overlaid book, OOS) to explain the IS/OOS split
    for label, c_t, x_t, b_t in [("A", default_tilt, default_tilt, default_tilt),
                                 ("T1", t1(), t1(), default_tilt)]:
        si, so, si_ov, so_ov = p3.build_book(c_t, x_t, b_t, oos_idx, isw_idx)
        print(f"\n{label} book: IS ov {si_ov['sharpe']:.2f} ({si_ov['cagr']*100:.2f}%)  "
              f"OOS ov {so_ov['sharpe']:.2f} ({so_ov['cagr']*100:.2f}%)  "
              f"OOS raw DD {so['maxdd']*100:.2f}%")

    with open(ROOT / "results" / "phase3_legs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["leg", "tilt", "IS_sh", "OOS_sh",
                                          "OOS_cagr", "OOS_dd", "OOS_vol"])
        w.writeheader()
        w.writerows(rows)
    print("\nSaved results/phase3_legs.csv")


if __name__ == "__main__":
    main()
