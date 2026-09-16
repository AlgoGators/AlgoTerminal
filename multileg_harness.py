"""Multi-leg F2 Tier 2: depth sizing with total notional caps.

Preregistered in research/multileg_f2_tier2.md. Variants:
V0 flat cap1.0; V1 depth 0.5/2.0 cap1.0; V2 depth 0.5/2.0 cap0.8;
V3 depth 0.25/1.5 cap1.0. Cross-leg stats, new-book stats vs
champion, one shuffled-depth control.
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
ENGINE = ROOT / "engine"
PANEL = ENGINE / "panel_v2.parquet"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

NC = 20
NC_SEED = 23
CROSS_LEGS = ["crack_321", "crack_gas", "crack_ho"]
VT = fb.VT_F2


def log(msg: str) -> None:
    print(msg, flush=True)


def multi_f2(levels, zl, variant, perm_depth: pd.Series | None = None):
    """Build capped multi-leg F2. Returns (agg_pos, agg_ret, agg_turn, leg_pos)."""
    k, max_dm, cap = variant
    leg_pos = {}
    leg_ret = {}
    leg_turn = {}
    for leg in CROSS_LEGS:
        lvl = levels[leg]
        z = zl[leg]
        on = (z <= -0.5).to_numpy(dtype=bool)
        zz = z.abs().to_numpy(dtype=float)
        if perm_depth is not None:
            mult = np.where(on, perm_depth.reindex(lvl.index).to_numpy()[np.arange(len(lvl))] * 0 + 1.0, 1.0)
            # perm_depth is already a shuffled multiplier series; use it where on
            mult = np.where(on, perm_depth.reindex(lvl.index).fillna(1.0).to_numpy(), 1.0)
        else:
            mult = np.where(on, np.clip(1 + k * (zz - 0.5), 1.0, max_dm), 1.0)
        raw = (pd.Series(np.where(on, 1.0, 0.0), index=lvl.index)
               * b4.fixed_vol_scale(lvl, VT))
        raw = raw * pd.Series(mult, index=lvl.index).shift(1).fillna(1.0)
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        leg_pos[leg] = p
        leg_ret[leg] = (p.shift(1).fillna(0.0) * lvl.diff()
                        / b4.base_of(lvl).shift(1).replace(0.0, np.nan)).fillna(0.0)
        leg_turn[leg] = p.diff().abs().fillna(0.0)
    # total notional cap
    total_abs = pd.DataFrame(leg_pos).abs().sum(axis=1)
    scale = (cap / total_abs.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    for leg in CROSS_LEGS:
        leg_pos[leg] = leg_pos[leg] * scale
        leg_ret[leg] = (leg_pos[leg].shift(1).fillna(0.0) * levels[leg].diff()
                        / b4.base_of(levels[leg]).shift(1).replace(0.0, np.nan)).fillna(0.0)
        leg_turn[leg] = leg_pos[leg].diff().abs().fillna(0.0)
    agg_pos = pd.DataFrame(leg_pos).sum(axis=1).rename("cross")
    agg_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0).rename("cross")
    agg_turn = pd.DataFrame(leg_turn).sum(axis=1).rename("cross")
    return agg_pos, agg_ret, agg_turn, scale


def book_stats_parts(parts, oos_idx, isw_idx):
    net = b4.apply_costs({k: v[0] for k, v in parts.items()},
                         {k: v[1] for k, v in parts.items()},
                         turnover={k: v[2] for k, v in parts.items()})
    for c in net.columns:
        net[c] = net[c].fillna(0.0)
    w = b4.weight_scheme(net[list(parts)], "EQ")
    bk = b4.book_returns(net, list(parts), w)
    si_r = b4.stats(bk.loc[isw_idx.intersection(bk.index)])
    so_r = b4.stats(bk.loc[oos_idx.intersection(bk.index)])
    si_o = b4.stats(b4.apply_overlay(bk).loc[isw_idx.intersection(bk.index)])
    so_o = b4.stats(b4.apply_overlay(bk).loc[oos_idx.intersection(bk.index)])
    return si_r, so_r, si_o, so_o


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    isw_idx = b4.window(pd.DataFrame(index=full_idx), b4.IS_START, full_idx.max()).index
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index

    fac4, rets4, turn4 = b4.build_v4(levels, None)
    zl = {k: fb.seasonal_z(levels[k]) for k in CROSS_LEGS}

    v1_cross = b4.apply_costs({"cross": fac4["cross_sectional"]},
                              {"cross": rets4["cross_sectional"]},
                              turnover={"cross": turn4["cross_sectional"]})["cross"]
    so_v1 = b4.stats(v1_cross.loc[oos_idx.intersection(v1_cross.index)])
    log(f"v1 single-most-crushed cross: OOS raw Sh {so_v1['sharpe']:.3f} "
        f"CAGR {so_v1['cagr']*100:.2f}% DD {so_v1['maxdd']*100:.2f}% vol {so_v1['vol']*100:.1f}%")
    champion_parts = {"crack_321": (fac4["crack_321"], rets4["crack_321"], turn4["crack_321"]),
                      "cross_sectional": (fac4["cross_sectional"], rets4["cross_sectional"], turn4["cross_sectional"]),
                      "bzwti": (fac4["bzwti"], rets4["bzwti"], turn4["bzwti"])}
    si_c, so_c, si_co, so_co = book_stats_parts(champion_parts, oos_idx, isw_idx)
    log(f"champion book: OOS raw Sh {so_c['sharpe']:.3f} CAGR {so_c['cagr']*100:.2f}% "
        f"DD {so_c['maxdd']*100:.2f}% | ov Sh {so_co['sharpe']:.3f} "
        f"CAGR {so_co['cagr']*100:.2f}% DD {so_co['maxdd']*100:.2f}%")

    variants = {"V0": (0.0, 1.0, 1.0), "V1": (0.5, 2.0, 1.0),
                "V2": (0.5, 2.0, 0.8), "V3": (0.25, 1.5, 1.0)}
    rows = []
    log("\nVariants:")
    for vid, variant in variants.items():
        agg_pos, agg_ret, agg_turn, scale = multi_f2(levels, zl, variant)
        net_leg = b4.apply_costs({"cross": agg_pos}, {"cross": agg_ret},
                                 turnover={"cross": agg_turn})
        sl = b4.stats(net_leg["cross"].loc[oos_idx.intersection(net_leg.index)])
        new_parts = {"crack_321": champion_parts["crack_321"],
                     "cross": (agg_pos, agg_ret, agg_turn),
                     "bzwti": champion_parts["bzwti"]}
        si_r, so_r, si_o, so_o = book_stats_parts(new_parts, oos_idx, isw_idx)
        log(f"  {vid}: cross OOS raw Sh {sl['sharpe']:.3f} CAGR {sl['cagr']*100:.2f}% "
            f"DD {sl['maxdd']*100:.2f}% vol {sl['vol']*100:.1f}%")
        log(f"       book OOS raw Sh {so_r['sharpe']:.3f} CAGR {so_r['cagr']*100:.2f}% "
            f"DD {so_r['maxdd']*100:.2f}% | ov Sh {so_o['sharpe']:.3f} "
            f"CAGR {so_o['cagr']*100:.2f}% DD {so_o['maxdd']*100:.2f}%  IS ov {si_o['sharpe']:.3f}")
        rows.append({"variant": vid, "leg_sharpe": sl["sharpe"], "leg_cagr": sl["cagr"],
                     "leg_dd": sl["maxdd"], "leg_vol": sl["vol"],
                     "book_raw_sharpe": so_r["sharpe"], "book_ov_sharpe": so_o["sharpe"],
                     "book_ov_dd": so_o["maxdd"], "book_is_ov_sharpe": si_o["sharpe"]})

    # control: shuffle depth multipliers among active days for V1
    log("\nControl (V1 depth shuffled, 20 seeds):")
    k, max_dm, cap = variants["V1"]
    on_days = np.zeros(len(full_idx), dtype=bool)
    for leg in CROSS_LEGS:
        on_days |= (zl[leg].to_numpy(dtype=float) <= -0.5)
    on_idx = np.flatnonzero(on_days)
    base_mult = np.ones(len(full_idx))
    for leg in CROSS_LEGS:
        zz = zl[leg].abs().to_numpy(dtype=float)
        on = zl[leg].to_numpy(dtype=float) <= -0.5
        base_mult[on] = np.maximum(base_mult[on], np.clip(1 + k * (zz[on] - 0.5), 1.0, max_dm))
    real = rows[1]["book_raw_sharpe"]
    nc = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        perm = rng.permutation(len(on_idx))
        shuf = base_mult.copy()
        shuf[on_idx] = base_mult[on_idx][perm]
        pdm = pd.Series(shuf, index=full_idx)
        agg_pos, agg_ret, agg_turn, _ = multi_f2(levels, zl, variants["V1"], perm_depth=pdm)
        new_parts = {"crack_321": champion_parts["crack_321"],
                     "cross": (agg_pos, agg_ret, agg_turn),
                     "bzwti": champion_parts["bzwti"]}
        so_r = book_stats_parts(new_parts, oos_idx, isw_idx)[1]
        nc.append(so_r["sharpe"] if not np.isnan(so_r["sharpe"]) else 0.0)
    log(f"  real V1 book raw OOS {real:.3f}  shuffled mean {np.mean(nc):.3f} "
        f"sd {np.std(nc):.3f}")
    rows.append({"variant": "NC_V1", "leg_sharpe": float(np.mean(nc)), "leg_cagr": float(np.std(nc)),
                 "leg_dd": real, "leg_vol": 0.0, "book_raw_sharpe": 0.0,
                 "book_ov_sharpe": 0.0, "book_ov_dd": 0.0, "book_is_ov_sharpe": 0.0})

    with open(ROOT / "results" / "multileg_f2_tier2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log("\nSaved results/multileg_f2_tier2.csv")


if __name__ == "__main__":
    main()
