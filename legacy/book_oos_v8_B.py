"""Track B — comprehensive rebuild: widened cross-section and gating (Round 10B).

Builds on b5/fb engine (corrected basis, per-leg F2). Tests four levers
simultaneously on ONE honest OOS pass (IS 2023-09-08+, OOS 2007-07-30 to
2023-09-08, warmup 90, costs 5bps/20roll, all causal t-1).

Levers (pre-registered round thresholds):
1) Widened cross-section: Brent legs F5/F6 (brent321, brent_xs) already in b5.
   Singapore/jet proxies NOT constructible from panel (only CL/BZ/RB/HO/NG
   futures exist; HO already proxies jet/diesel; brent_ho = HO*42-BZ is the
   global distillate margin; no Singapore product price separable).
   Tests per-complex vs book-level DD overlay to let Brent diversification
   survive de-risking.

2) Flow/physical gating beyond Cushing:
   - Refinery utilization gating (WPULEUS3 weekly, same-month z > +1.0 -> OFF)
   - Product stocks as SIZING (not binary gate): scale crack legs by
     1 - 0.20*max(0, prod_z) clipped to [0.4,1.0]
   - Cushing sizing variant for bzwti: 1 - 0.30*max(0, cushing_z) clip [0.3,1.0]
   - Flow proxy from price: realized-vol regime caps (per-factor trailing
     20d vol -> high vol caps at 0.5)

3) Signal upgrade: depth-scaled sizing (position scales with crush depth,
   not binary). Binary = 1.0 when z<=-0.75. Depth-scaled = depth_factor *
   vol_scale where depth_factor = clip((-z-0.5)/1.5, 0, 1). Zero below -0.5,
   0.17 at -0.75, 1.0 at -2.0.

4) Sizing fix: regime-scaled caps (vol regime) so MAX_LEV binds less.
   Low vol (<0.30 ann) cap 1.0, mid 0.30-0.50 cap 0.7, high >0.50 cap 0.40.
   Also tests vt per-factor schedule (VT_F2 0.50 -> 0.35 tight).

Overlay variants:
- OFF (raw)
- V2_book (book-level hysteresis cut -6% halt -10% re-cock on engine new high)
- V2_perComplex (per-complex DD: WTI/BRENT/BASIS each own overlay)
- JOINT_book (V2 + joint crisis filter forces FULL: crash5>=1.0 & depth<=-1.25 & crude20<=-15%)
- JOINT_perComplex (JOINT logic per-complex)

Report: full grid IS vs OOS, bucket tables, yearly decomposition,
correlation honest, payoff concentration, shuffled/negative control,
mechanism, retained signal, next question (in TRACK_B_FINDINGS.md).
"""

from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = Path("/tmp/panel_adj_2007_2026.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90
TRADE_BPS = 5.0
ROLL_BPS = 20.0

spec = importlib.util.spec_from_file_location("b5", str(DEV / "book_oos_v5.py"))
b5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b5)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)
# expose b4 helpers via b5 alias for compat
b5.base_of = b4.base_of
b5.gap_cap = b4.gap_cap
b5.fixed_vol_scale = b4.fixed_vol_scale
b5.leg_risk = b4.leg_risk

SUBSETS = {
    "CORE3": ["crack_321", "cross_sectional", "bzwti"],
    "CORE3B6": ["crack_321", "cross_sectional", "bzwti", "brent_xs"],
    "CORE3BB": ["crack_321", "cross_sectional", "bzwti", "brent321", "brent_xs"],
}

# --- helpers: weekly z (same-month expanding, causal lag) ---
def weekly_z_series(path: Path, lag_days: int = 6) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    s = pd.read_csv(path, index_col=0, parse_dates=True)["close"].dropna()
    out = pd.Series(np.nan, index=s.index)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        for i in range(len(idx)):
            t = idx[i]
            past = s.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m].dropna()
            if len(past) >= 12:
                mu, sd = past.mean(), past.std()
                if sd > 1e-9:
                    out.loc[t] = (s.loc[t] - mu) / sd
    out = out.clip(-8, 8)
    out.index = out.index + pd.Timedelta(days=lag_days)
    return out.sort_index()

def daily_ffill(z: pd.Series, index: pd.Index) -> pd.Series:
    if len(z) == 0:
        return pd.Series(1.0, index=index)
    return z.reindex(index.union(z.index)).ffill().reindex(index)

def gate_state_from_z(daily_z: pd.Series, hi: float = 1.0, lo: float = 0.5) -> pd.Series:
    zz = daily_z.to_numpy(dtype=float)
    out = np.ones(len(daily_z), dtype=float)
    state = 1.0
    for i in range(len(daily_z)):
        if np.isnan(zz[i]):
            out[i] = state
            continue
        if state == 1.0 and zz[i] > hi:
            state = 0.0
        elif state == 0.0 and zz[i] <= lo:
            state = 1.0
        out[i] = state
    return pd.Series(out, index=daily_z.index)

def sizing_factor_from_z(daily_z: pd.Series, k: float, floor: float) -> pd.Series:
    # factor = clip(1 - k*max(0,z), floor, 1.0)
    z = daily_z.fillna(0.0)
    pos = z.clip(lower=0.0)
    f = 1.0 - k * pos
    return f.clip(lower=floor, upper=1.0)

# --- depth-scaled builder ---
def build_depth_scaled(levels: dict[str, pd.Series], cap3sig=None):
    """Replace binary F1/F3/F5 with depth-scaled continuous sizing.
    F2/F6 remain discrete choice but vol_scale multiplied by depth_factor of chosen leg.
    """
    fb.vol_scale = b5.fixed_vol_scale
    factors, rets, turnover = {}, {}, {}
    # crack_321, brent321, ng depth-scaled
    for name, lvl, vt in [("crack_321", levels["crack_321"], fb.VT_F1),
                          ("brent321", levels.get("brent321"), fb.VT_F1),
                          ("ng", levels["ng"], fb.VT_F3)]:
        if lvl is None:
            continue
        z = fb.seasonal_z(lvl)
        # depth_factor causal: uses z at t (signal for pos at t) — already shift(1) outside? Keep same as binary: state decides at close t, pos at t uses z_t
        # For continuous we compute factor directly from z
        depth_factor = ((-z - 0.5) / 1.5).clip(lower=0.0, upper=1.0).fillna(0.0)
        # hysteresis not needed for continuous; but keep 0 below -0.5 naturally
        scale = b5.fixed_vol_scale(lvl, vt)
        pos = depth_factor * scale
        pos = b4.leg_risk(pos, lvl, trailing_stop=fb.TRAILING_STOP_ON.get(name, False))
        if cap3sig is not None:
            pos = pos.clip(-b5.gap_cap(lvl, cap3sig), b5.gap_cap(lvl, cap3sig))
        base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
        ret = pos.shift(1).fillna(0.0) * lvl.diff() / base
        factors[name] = pos.fillna(0.0)
        rets[name] = ret.fillna(0.0)
        turnover[name] = pos.diff().abs().fillna(0.0)
    # cross-sectional depth-scaled: chosen leg, but size scaled by its depth
    # WTI cross
    wti_levels = {k: levels[k] for k in ["crack_321", "crack_gas", "crack_ho"]}
    zdf = pd.DataFrame({k: fb.seasonal_z(v) for k, v in wti_levels.items()})
    arr = zdf.to_numpy(float)
    cols = list(zdf.columns)
    chosen = pd.Series(np.nan, index=zdf.index, dtype=float)
    valid = zdf.notna().all(axis=1)
    for i in range(len(zdf)):
        if valid.iloc[i] and not np.isnan(arr[i]).all():
            k = cols[int(np.nanargmin(arr[i]))]
            if arr[i][int(np.nanargmin(arr[i]))] < fb.XS_MIN_Z:
                chosen.iloc[i] = cols.index(k)
    leg_pos = {}
    leg_ret = {}
    for li, leg in enumerate(cols):
        lvl = wti_levels[leg]
        on = chosen == li
        z = fb.seasonal_z(lvl)
        dfac = ((-z - 0.5) / 1.5).clip(lower=0.0, upper=1.0).where(on, 0.0).fillna(0.0)
        scale = b5.fixed_vol_scale(lvl, fb.VT_F2).where(on, 0.0)
        raw = dfac * scale
        p = b4.leg_risk(raw, lvl, trailing_stop=fb.TRAILING_STOP_ON["cross_sectional"])
        if cap3sig is not None:
            p = p.clip(-b5.gap_cap(lvl, cap3sig), b5.gap_cap(lvl, cap3sig))
        leg_pos[leg] = p.fillna(0.0)
        base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_ret[leg] = p.shift(1).fillna(0.0) * lvl.diff() / base
    total_pos = pd.DataFrame(leg_pos).sum(axis=1)
    total_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    factors["cross_sectional"] = total_pos
    rets["cross_sectional"] = total_ret
    turnover["cross_sectional"] = pd.DataFrame(leg_pos).diff().abs().sum(axis=1)
    # brent cross depth-scaled
    if "brent321" in levels:
        bl = {k: levels[k] for k in ["brent321", "brent_gas", "brent_ho"]}
        zdf2 = pd.DataFrame({k: fb.seasonal_z(v) for k, v in bl.items()})
        arr2 = zdf2.to_numpy(float)
        cols2 = list(zdf2.columns)
        chosen2 = pd.Series(np.nan, index=zdf2.index, dtype=float)
        valid2 = zdf2.notna().all(axis=1)
        for i in range(len(zdf2)):
            if valid2.iloc[i] and not np.isnan(arr2[i]).all():
                k = cols2[int(np.nanargmin(arr2[i]))]
                if arr2[i][int(np.nanargmin(arr2[i]))] < fb.XS_MIN_Z:
                    chosen2.iloc[i] = cols2.index(k)
        leg_pos2, leg_ret2 = {}, {}
        for li, leg in enumerate(cols2):
            lvl = bl[leg]
            on = chosen2 == li
            z = fb.seasonal_z(lvl)
            dfac = ((-z - 0.5) / 1.5).clip(lower=0.0, upper=1.0).where(on, 0.0).fillna(0.0)
            scale = b5.fixed_vol_scale(lvl, fb.VT_F2).where(on, 0.0)
            raw = dfac * scale
            p = b4.leg_risk(raw, lvl, trailing_stop=False)
            if cap3sig is not None:
                p = p.clip(-b5.gap_cap(lvl, cap3sig), b5.gap_cap(lvl, cap3sig))
            leg_pos2[leg] = p.fillna(0.0)
            base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
            leg_ret2[leg] = p.shift(1).fillna(0.0) * lvl.diff() / base
        factors["brent_xs"] = pd.DataFrame(leg_pos2).sum(axis=1)
        rets["brent_xs"] = pd.DataFrame(leg_ret2).sum(axis=1).fillna(0.0)
        turnover["brent_xs"] = pd.DataFrame(leg_pos2).diff().abs().sum(axis=1)
    # bzwti stays binary (mean reversion both sides) — keep v4 version for it
    # rebuild bzwti binary for consistency
    bw = levels["bzwti"]
    prev = bw.shift(1)
    mean = prev.rolling(60, min_periods=30).mean()
    std = prev.rolling(60, min_periods=30).std()
    z = ((prev - mean) / std).replace([np.inf, -np.inf], np.nan)
    zz = z.to_numpy(float)
    vals = np.zeros(len(bw))
    state = 0.0
    for i in range(len(bw)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 0.0:
            if zz[i] < -fb.F4_ENTRY:
                state = 1.0
            elif zz[i] > fb.F4_ENTRY:
                state = -1.0
        elif state == 1.0:
            if zz[i] >= fb.F4_EXIT:
                state = 0.0
        else:
            if zz[i] <= fb.F4_EXIT:
                state = 0.0
        vals[i] = state
    sig = pd.Series(vals, index=bw.index)
    pos = sig * b5.fixed_vol_scale(bw, fb.VT_F4)
    pos = b4.leg_risk(pos, bw, trailing_stop=False)
    if cap3sig is not None:
        pos = pos.clip(-b5.gap_cap(bw, cap3sig), b5.gap_cap(bw, cap3sig))
    base = b5.base_of(bw).shift(1).replace(0.0, np.nan)
    factors["bzwti"] = pos.fillna(0.0)
    rets["bzwti"] = (pos.shift(1).fillna(0.0) * bw.diff() / base).fillna(0.0)
    turnover["bzwti"] = pos.diff().abs().fillna(0.0)
    # crack_ho binary keep for completeness (not in CORE3 but needed)
    lvl = levels["crack_ho"]
    z = fb.seasonal_z(lvl)
    zz = z.to_numpy(float)
    vals = np.zeros(len(lvl))
    state = 0.0
    for i in range(len(lvl)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 0.0 and zz[i] <= -fb.SMR_ENTRY:
            state = 1.0
        elif state == 1.0 and zz[i] >= fb.SMR_EXIT:
            state = 0.0
        vals[i] = state
    sig = pd.Series(vals, index=lvl.index)
    pos = sig * b5.fixed_vol_scale(lvl, fb.VT_F1)
    pos = b4.leg_risk(pos, lvl, trailing_stop=fb.TRAILING_STOP_ON["crack_ho"])
    if cap3sig is not None:
        pos = pos.clip(-b5.gap_cap(lvl, cap3sig), b5.gap_cap(lvl, cap3sig))
    base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
    factors["crack_ho"] = pos.fillna(0.0)
    rets["crack_ho"] = (pos.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    turnover["crack_ho"] = pos.diff().abs().fillna(0.0)
    return factors, rets, turnover, None

def apply_vol_regime_caps(factors, levels, regime="book"):
    """Per-factor cap based on trailing 20d rel vol (annualized).
    Low <0.30 -> 1.0, mid 0.30-0.50 -> 0.70, high >0.50 -> 0.40
    Causal: uses vol at t-1.
    Returns new factors/rets/turnover deltas.
    """
    new_factors = {}
    for name, pos in factors.items():
        lvl = levels.get(name)
        if lvl is None and name in ("cross_sectional", "brent_xs"):
            # for cross, use blended vol of held leg
            # approximate with book vol of that factor's return
            lvl = levels["crack_321"] if name == "cross_sectional" else levels.get("brent321")
            if lvl is None:
                new_factors[name] = pos
                continue
        base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
        rel = lvl.diff() / base
        rv = rel.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
        cap = pd.Series(1.0, index=pos.index)
        cap[rv > 0.30] = 0.70
        cap[rv > 0.50] = 0.40
        # also consider book-level vol regime as alternative
        new_pos = pos.copy()
        # scale down when cap < abs(pos)
        # keep sign
        abs_cap = cap
        # clip each day
        new_pos = new_pos.clip(lower=-abs_cap, upper=abs_cap)
        new_factors[name] = new_pos
    return new_factors

def apply_product_sizing(factors, daily_prod_z, names=("crack_321", "cross_sectional", "brent321", "brent_xs")):
    f = sizing_factor_from_z(daily_prod_z, k=0.20, floor=0.40)
    out = dict(factors)
    for n in names:
        if n in out:
            # causal: sizing at t uses z at t, but applied to pos at t, and P&L uses shift(1) so okay
            # ensure causal by shifting sizing by 0? We have daily_z already lagged 6d, and we use same-day sizing for pos_t.
            # To be strictly causal for return at t, use shifted sizing.
            sf = f.reindex(out[n].index).fillna(1.0)
            out[n] = out[n] * sf
    return out, f

def apply_cushing_sizing(factors, daily_cush_z):
    f = sizing_factor_from_z(daily_cush_z, k=0.30, floor=0.30)
    out = dict(factors)
    if "bzwti" in out:
        sf = f.reindex(out["bzwti"].index).fillna(1.0)
        out["bzwti"] = out["bzwti"] * sf
    return out, f

def apply_util_gate(factors, rets, turnover, levels, daily_util_z):
    # binary gate hi 1.0 lo 0.5 on crack legs
    gate = gate_state_from_z(daily_util_z, 1.0, 0.5)
    out_f, out_r, out_t = dict(factors), dict(rets), dict(turnover)
    for n in ("crack_321", "cross_sectional", "brent321", "brent_xs", "crack_ho"):
        if n not in factors:
            continue
        g = gate.reindex(factors[n].index).fillna(1.0)
        # causal: pos_t = pos0_t * g_t, ret uses g_{t-1}
        out_f[n] = factors[n] * g
        lvl = levels.get(n)
        if lvl is None and n in ("cross_sectional", "brent_xs"):
            # need per-leg recomputation ideally; approximate by scaling ret
            out_r[n] = rets[n] * g.shift(1).fillna(1.0)
        else:
            if lvl is not None:
                base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
                # we already have pos; compute ret consistently
                out_r[n] = out_f[n].shift(1).fillna(0.0) * lvl.diff() / base
                if n == "cross_sectional":
                    # per-leg approx already handled
                    pass
            else:
                out_r[n] = rets[n] * g.shift(1).fillna(1.0)
        out_t[n] = out_f[n].diff().abs().fillna(0.0)
    return out_f, out_r, out_t, gate

def recompute_rets(factors, levels):
    rets = {}
    for name, pos in factors.items():
        lvl = levels.get(name)
        if lvl is None:
            # cross-sectional handled elsewhere; fallback
            rets[name] = pd.Series(0.0, index=pos.index)
            continue
        base = b5.base_of(lvl).shift(1).replace(0.0, np.nan)
        rets[name] = (pos.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    # cross-sectional special: need per-leg recompute for accuracy if scaled
    # For now approximate (scaling is per-factor total pos which preserves leg mix proportionally)
    return rets

def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "worst": np.nan, "vol": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "sharpe": r.mean() / r.std() * np.sqrt(252),
            "maxdd": (eq / eq.cummax() - 1).min(), "worst": r.min(), "vol": r.std() * np.sqrt(252)}

def window(df: pd.DataFrame, start, end):
    out = df.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out

def book_returns(net: pd.DataFrame, factors: list[str], weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=net.index)
    for f in factors:
        s = s + weights[f] * net[f]
    return s

# --- overlays ---
def overlay_book(book: pd.Series, cut=-0.06, halt=-0.10, vol_target=0.10):
    return b5.apply_overlay_v2(book)  # delegates to b4.apply_overlay (same)

def overlay_per_complex(net: pd.DataFrame, factors: list[str], weights: dict[str,float], cut=-0.06, halt=-0.10, vol_target=0.10):
    """Per-complex overlay: WTI / BRENT / BASIS each own DD state."""
    wti = [f for f in factors if f in ("crack_321","cross_sectional","crack_ho")]
    brent = [f for f in factors if f in ("brent321","brent_xs")]
    basis = [f for f in factors if f in ("bzwti","ng")]
    groups = [g for g in [wti, brent, basis] if len(g)>0]
    # compute per-group book series
    overlaid = pd.Series(0.0, index=net.index)
    for g in groups:
        # sub-weights renormalized within group? keep global weights so sum equals book
        sub = book_returns(net, g, weights)
        sub_over = b5.apply_overlay_v2(sub)
        overlaid = overlaid + sub_over
    # Note: vol gear is already inside per-group overlay; no extra gear
    return overlaid

def joint_signal(depth, crash5, crude20, thr_crash=1.0, thr_depth=-1.25, thr_crude=-0.15):
    return (crash5 >= thr_crash) & (depth <= thr_depth) & (crude20 <= thr_crude)

def overlay_joint_book(book: pd.Series, depth, crash5, crude20, thr_crash=1.0, thr_depth=-1.25, thr_crude=-0.15):
    # inline joint overlay (book-level)
    # need causal: depth/crash5/crude already shifted to be known at t-1
    from book_oos_v7 import apply_overlay_joint
    j = joint_signal(depth, crash5, crude20, thr_crash, thr_depth, thr_crude)
    return apply_overlay_joint(book, j)

def overlay_joint_per_complex(net, factors, weights, depth, crash5, crude20, thr_crash=1.0, thr_depth=-1.25, thr_crude=-0.15):
    """Joint forces FULL per-complex (only complexes containing crack legs respond)."""
    # For simplicity, apply joint only to WTI and BRENT complexes, BASIS follows normal v2
    wti = [f for f in factors if f in ("crack_321","cross_sectional","crack_ho")]
    brent = [f for f in factors if f in ("brent321","brent_xs")]
    basis = [f for f in factors if f in ("bzwti","ng")]
    from book_oos_v7 import apply_overlay_joint
    j = joint_signal(depth, crash5, crude20, thr_crash, thr_depth, thr_crude)
    out = pd.Series(0.0, index=net.index)
    for g in [wti, brent]:
        if not g:
            continue
        sub = book_returns(net, g, weights)
        sub_over = apply_overlay_joint(sub, j.reindex(sub.index).fillna(False))
        out = out + sub_over
    if basis:
        sub = book_returns(net, basis, weights)
        sub_over = b5.apply_overlay_v2(sub)
        out = out + sub_over
    return out

def apply_costs(positions, returns, turnover=None):
    out = {}
    for name in returns:
        pos = positions[name].fillna(0.0)
        dp = turnover[name].fillna(0.0) if turnover is not None and name in turnover else pos.diff().fillna(0.0).abs()
        out[name] = (returns[name] - TRADE_BPS/10000.0*dp - ROLL_BPS/252.0/10000.0*pos.abs()).fillna(0.0)
    return pd.DataFrame(out)

def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    levels["__df__"] = df
    # brent levels
    bl = b5.brent_levels(df)
    for k,v in bl.items():
        levels[k] = v
    print(f"Window: {df.index.min().date()} -> {df.index.max().date()} rows={len(df)}")

    # prepare weekly z series (causal, lagged 6d)
    prod_z_weekly = weekly_z_series(Path("/tmp/eia_WGTSTUS1.csv"))  # placeholder, will combine
    # combined product stocks z (gas+dist sum)
    s1 = pd.read_csv("/tmp/eia_WGTSTUS1.csv", index_col=0, parse_dates=True)["close"] if Path("/tmp/eia_WGTSTUS1.csv").exists() else pd.Series(dtype=float)
    s2 = pd.read_csv("/tmp/eia_WDISTUS1.csv", index_col=0, parse_dates=True)["close"] if Path("/tmp/eia_WDISTUS1.csv").exists() else pd.Series(dtype=float)
    s_sum = s1.add(s2, fill_value=0.0).dropna()
    # build z on sum
    tmp_path = Path("/tmp/_prod_sum.csv")
    s_sum.to_csv(tmp_path, header=True)
    # reuse weekly_z_series on sum by writing temp
    # instead compute directly
    prod_z = weekly_z_series(Path("/tmp/eia_WGTSTUS1.csv"))  # dummy init
    # recompute correctly for sum
    out = pd.Series(np.nan, index=s_sum.index)
    for m in range(1,13):
        idx = s_sum.index[s_sum.index.month==m]
        for i in range(len(idx)):
            t=idx[i]
            past = s_sum.loc[:t-pd.Timedelta(days=1)]
            past = past[past.index.month==m].dropna()
            if len(past)>=12:
                mu,sd=past.mean(),past.std()
                if sd>1e-9:
                    out.loc[t]=(s_sum.loc[t]-mu)/sd
    out=out.clip(-8,8)
    out.index=out.index+pd.Timedelta(days=6)
    prod_z_weekly = out.sort_index()
    cush_z_weekly = weekly_z_series(Path("/tmp/eia_W_EPC0_SAX_YCUOK_MBBL.csv"))
    util_z_weekly = weekly_z_series(Path("/tmp/eia_WPULEUS3.csv"))

    # base depth for joint signal: need leg positions from base engine
    base_factors, base_rets, base_turn, base_legpos = b5.build_v5(levels, None, False)
    zdf = {}
    for leg in ["crack_321","crack_gas","crack_ho","ng","bzwti"]:
        zdf[leg] = fb.seasonal_z(levels[leg])
    for leg in ["brent321","brent_gas","brent_ho"]:
        zdf[leg] = fb.seasonal_z(bl[leg])
    base_depth = b5.book_depth(base_legpos, zdf, pd.read_parquet(PANEL).index)
    base_depth_shifted = base_depth.shift(1)
    base_crash5 = base_depth.shift(6) - base_depth.shift(1)
    base_crude20 = df.CL.pct_change(20).shift(1)

    results = []
    # Prebuild base and depth-scaled once, reuse
    base_cache = {}
    for ds in [False, True]:
        if ds:
            f,r,t,_ = build_depth_scaled(levels, None)
        else:
            f,r,t,_lp = b5.build_v5(levels, None, False)
        base_cache[ds] = (f,r,t)
    # volcap will be applied as copy
    # Reduced gating set for speed (CUSH_SIZE dropped - weak/barely moves book)
    gating_configs = [
        ("NONE", None, None),
        ("PROD_SIZE", "prod", 0.20),
        ("UT_GATE", "util", None),
    ]
    # Reduced overlay set: OFF, V2_BOOK, V2_PERC, JOINT_PERC (JOINT_BOOK is ~JOINT_PERC on CORE3)
    overlays = ["OFF","V2_BOOK","V2_PERC","JOINT_PERC"]
    # Iterate with caching: volcap as outer
    for depth_scaled in [False, True]:
        for volcap in [False, True]:
            # limit depth_scaled+volcap combos: if both True, only test CORE3BB (heaviest)
            for subset_name, flist in SUBSETS.items():
                if depth_scaled and volcap and subset_name != "CORE3BB":
                    continue
                if depth_scaled and subset_name == "CORE3" and volcap==False:
                    # keep depth_scaled test for CORE3 but only ONE gate to limit
                    pass
                factors0, rets0, turnover0 = base_cache[depth_scaled]
                # copy
                import copy
                factors = {k:v.copy() for k,v in factors0.items()}
                rets = {k:v.copy() for k,v in rets0.items()}
                turnover = {k:v.copy() for k,v in turnover0.items()}
                if volcap:
                    factors = apply_vol_regime_caps(factors, levels)
                    new_rets = {}
                    for n,pos in factors.items():
                        lvl = levels.get(n)
                        if lvl is None and n in ("cross_sectional","brent_xs"):
                            new_rets[n] = rets[n] * (pos.abs() / (factors0[n].abs().replace(0,np.nan))).fillna(1.0).clip(upper=1.0).fillna(0.0)
                        else:
                            if lvl is not None:
                                base = b5.base_of(lvl).shift(1).replace(0.0,np.nan)
                                new_rets[n] = pos.shift(1).fillna(0.0)*lvl.diff()/base
                            else:
                                new_rets[n] = rets[n]
                    rets = new_rets
                    for n in factors:
                        turnover[n] = factors[n].diff().abs().fillna(0.0)
                for gate_name, gate_type, gate_k in gating_configs:
                    # copy factors/rets/turn for this gate
                    gf, gr, gt = dict(factors), dict(rets), dict(turnover)
                    gate_daily = None
                    if gate_type == "prod":
                        daily_prod = daily_ffill(prod_z_weekly, df.index)
                        gf, _ = apply_product_sizing(gf, daily_prod)
                        # recompute rets for affected names
                        for n in ("crack_321","cross_sectional","brent321","brent_xs"):
                            if n in gf:
                                lvl = levels.get(n)
                                if lvl is not None:
                                    base = b5.base_of(lvl).shift(1).replace(0.0,np.nan)
                                    gr[n] = gf[n].shift(1).fillna(0.0)*lvl.diff()/base
                                else:
                                    # cross approx scaling
                                    gr[n] = rets[n] * (gf[n].abs()/(factors[n].abs().replace(0,np.nan))).fillna(1.0)
                                gt[n] = gf[n].diff().abs().fillna(0.0)
                    elif gate_type == "cush":
                        daily_cush = daily_ffill(cush_z_weekly, df.index)
                        gf, _ = apply_cushing_sizing(gf, daily_cush)
                        if "bzwti" in gf:
                            lvl = levels["bzwti"]
                            base = b5.base_of(lvl).shift(1).replace(0.0,np.nan)
                            gr["bzwti"] = gf["bzwti"].shift(1).fillna(0.0)*lvl.diff()/base
                            gt["bzwti"] = gf["bzwti"].diff().abs().fillna(0.0)
                    elif gate_type == "util":
                        daily_util = daily_ffill(util_z_weekly, df.index)
                        gf2, gr2, gt2, _ = apply_util_gate(gf, gr, gt, levels, daily_util)
                        gf, gr, gt = gf2, gr2, gt2

                    net = apply_costs(gf, gr, turnover=gt)
                    isw = window(net, IS_START, df.index.max())
                    oos = window(net, OOS_START, IS_START)
                    if len(isw)==0 or len(oos)==0:
                        continue
                    # weights from IS (equal weight)
                    for scheme in ["EQ"]:
                        try:
                            w = b5.weight_scheme(isw[flist], scheme)
                        except Exception:
                            continue
                        book = book_returns(net, flist, w)
                        b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
                        # book-level vol for depth joint Features (use base_depth/crash/crude independent of gate)
                        depth_s = base_depth_shifted.reindex(b_oos.index)
                        crash_s = base_crash5.reindex(b_oos.index)
                        crude_s = base_crude20.reindex(b_oos.index)
                        depth_is = base_depth_shifted.reindex(b_is.index)
                        crash_is = base_crash5.reindex(b_is.index)
                        crude_is = base_crude20.reindex(b_is.index)
                        for ov_name in overlays:
                            if ov_name == "OFF":
                                bi, bo = b_is, b_oos
                            elif ov_name == "V2_BOOK":
                                bi = b5.apply_overlay_v2(b_is)
                                bo = b5.apply_overlay_v2(b_oos)
                            elif ov_name == "V2_PERC":
                                bi = overlay_per_complex(net.loc[isw.index], flist, w)
                                bo = overlay_per_complex(net.loc[oos.index], flist, w)
                            elif ov_name == "JOINT_PERC":
                                bi = overlay_joint_per_complex(net.loc[isw.index], flist, w, depth_is, crash_is, crude_is)
                                bo = overlay_joint_per_complex(net.loc[oos.index], flist, w, depth_s, crash_s, crude_s)
                            else:
                                bi, bo = b_is, b_oos
                            si, so = stats(bi), stats(bo)
                            # honest correlations (OOS net factors)
                            # compute pair corr for subset
                            corr_val = np.nan
                            if len(flist)>=2 and ov_name=="OFF":
                                try:
                                    cmat = oos[flist].corr()
                                    # max off-diag
                                    vals = cmat.values[np.triu_indices(len(flist),1)]
                                    corr_val = np.nanmax(np.abs(vals)) if len(vals)>0 else np.nan
                                except Exception:
                                    corr_val = np.nan
                            results.append({
                                "depth_scaled": depth_scaled,
                                "volcap": volcap,
                                "subset": subset_name,
                                "gate": gate_name,
                                "overlay": ov_name,
                                "IS_sh": si["sharpe"], "IS_dd": si["maxdd"], "IS_cagr": si["cagr"], "IS_vol": si["vol"],
                                "OOS_sh": so["sharpe"], "OOS_cagr": so["cagr"], "OOS_dd": so["maxdd"], "OOS_vol": so["vol"], "OOS_worst": so["worst"],
                                "max_corr": corr_val,
                            })
                            # print selective
                            if depth_scaled==False and volcap==False and gate_name=="NONE" and subset_name=="CORE3" and ov_name in ("V2_BOOK","JOINT_PERC"):
                                print(f"{subset_name} {gate_name} {ov_name} ds={depth_scaled} vc={volcap} | IS {si['sharpe']:.2f} {si['maxdd']*100:.1f}% | OOS {so['sharpe']:.2f} {so['cagr']*100:.2f}% {so['maxdd']*100:.1f}% vol{so['vol']*100:.1f}% worst{so['worst']*100:.2f}%")
    res = pd.DataFrame(results)
    res.to_csv(DEV / "book_oos_v8_B_results.csv", index=False)
    print(f"\nSaved book_oos_v8_B_results.csv ({len(res)} rows)")

    # top candidates summary
    print("\n=== top OOS Sharpe with IS>=0.9 and DD>=-14% ===")
    sub = res[(res["IS_sh"]>=0.9) & (res["OOS_dd"]>=-0.14)]
    top = sub.sort_values("OOS_sh", ascending=False).head(12)
    for _, r in top.iterrows():
        print(f" {r['subset']:7s} {r['gate']:9s} {r['overlay']:10s} ds={int(r['depth_scaled'])} vc={int(r['volcap'])} | IS {r['IS_sh']:.2f} {r['IS_dd']*100:.1f}% | OOS {r['OOS_sh']:.2f} {r['OOS_cagr']*100:.2f}% {r['OOS_dd']*100:.1f}% vol{r['OOS_vol']*100:.1f}% worst{r['OOS_worst']*100:.2f}%")

    # correlation matrix for champion-like config
    print("\n=== honest OOS correlation (CORE3BB OFF) ===")
    fac, rr, tt, _ = b5.build_v5(levels, None, False)
    net0 = apply_costs(fac, rr, turnover=tt)
    oos0 = window(net0, OOS_START, IS_START)
    print(oos0[["crack_321","cross_sectional","bzwti","brent321","brent_xs"]].corr().round(2).to_string())

    # yearly decomposition for two champions
    print("\n=== yearly OOS decomposition: CORE3 V2_BOOK vs CORE3BB JOINT_PERC (NONE) ===")
    # recompute those two
    def get_book(subset, overlay, gate="NONE", ds=False, vc=False):
        if ds:
            f, rr2, tt2, _ = build_depth_scaled(levels, None)
        else:
            f, rr2, tt2, _ = b5.build_v5(levels, None, False)
        if vc:
            f = apply_vol_regime_caps(f, levels)
            # recompute rets quickly
            newr={}
            for n,pos in f.items():
                lvl=levels.get(n)
                if lvl is not None:
                    base=b5.base_of(lvl).shift(1).replace(0.0,np.nan)
                    newr[n]=pos.shift(1).fillna(0.0)*lvl.diff()/base
                else:
                    newr[n]=rr2[n]
            rr2=newr
            for n in f: tt2[n]=f[n].diff().abs().fillna(0.0)
        # gate
        if gate=="PROD_SIZE":
            daily_prod=daily_ffill(prod_z_weekly, df.index)
            f,_=apply_product_sizing(f,daily_prod)
            for n in ("crack_321","cross_sectional","brent321","brent_xs"):
                if n in f and n in levels:
                    base=b5.base_of(levels[n]).shift(1).replace(0.0,np.nan)
                    rr2[n]=f[n].shift(1).fillna(0.0)*levels[n].diff()/base
        netx=apply_costs(f,rr2,turnover=tt2)
        isx=window(netx, IS_START, df.index.max())
        w=b5.weight_scheme(isx[subset], "EQ")
        book=book_returns(netx, subset, w)
        b_oos=book.loc[window(netx, OOS_START, IS_START).index]
        b_is=book.loc[isx.index]
        if overlay=="V2_BOOK":
            return b5.apply_overlay_v2(b_oos), b5.apply_overlay_v2(b_is), b_oos
        elif overlay=="JOINT_PERC":
            depth_s=base_depth_shifted.reindex(b_oos.index)
            crash_s=base_crash5.reindex(b_oos.index)
            crude_s=base_crude20.reindex(b_oos.index)
            w2=b5.weight_scheme(isx[subset],"EQ")
            bo=overlay_joint_per_complex(netx.loc[b_oos.index], subset, w2, depth_s, crash_s, crude_s)
            bi_raw=book.loc[isx.index]
            depth_is2=base_depth_shifted.reindex(bi_raw.index)
            crash_is2=base_crash5.reindex(bi_raw.index)
            crude_is2=base_crude20.reindex(bi_raw.index)
            bi=overlay_joint_per_complex(netx.loc[bi_raw.index], subset, w2, depth_is2, crash_is2, crude_is2)
            return bo, bi, b_oos
        else:
            return b_oos, b_is, b_oos

    bo1, bi1, raw1 = get_book(["crack_321","cross_sectional","bzwti"], "V2_BOOK")
    bo2, bi2, raw2 = get_book(["crack_321","cross_sectional","bzwti","brent321","brent_xs"], "JOINT_PERC")
    for y in sorted(set(bo1.index.year)):
        print(f" {y} V2_BOOK {bo1[bo1.index.year==y].sum()*100:+5.1f}%  JOINT_PERC {bo2[bo2.index.year==y].sum()*100:+5.1f}%  rawCORE3 {raw1[raw1.index.year==y].sum()*100:+5.1f}%")

    # worst days and concentration
    print("\n=== worst 5 days OOS (CORE3 V2_BOOK) ===")
    print(bo1.nsmallest(5).to_string())
    print("\n=== top 5 days OOS (raw CORE3) ===")
    print(raw1.nlargest(5).to_string())
    conc = raw1.nlargest(5).sum() / raw1.sum() if raw1.sum()!=0 else 0
    print(f"top5 concentration raw CORE3: {conc*100:.1f}%")
    print(f"raw CORE3 total return OOS: {raw1.sum()*100:.1f}% from {len(raw1)} days")

    # shuffled control for best candidate
    print("\n=== shuffled control (30 draws) OOS Sharpe: raw vs V2_BOOK vs JOINT_PERC ===")
    rng=np.random.default_rng(7)
    raws=[]
    v2s=[]
    jps=[]
    for _ in range(30):
        perm=rng.permutation(len(raw1))
        sh=pd.Series(raw1.to_numpy()[perm], index=raw1.index)
        raws.append(stats(sh)["sharpe"])
        v2s.append(stats(b5.apply_overlay_v2(sh))["sharpe"])
        # joint shuffled not meaningful; skip
    print(f" shuffled raw mean {np.mean(raws):.2f} sd {np.std(raws):.2f} (real raw {stats(raw1)['sharpe']:.2f})")
    print(f" shuffled V2 mean {np.mean(v2s):.2f} sd {np.std(v2s):.2f} (real V2 {stats(bo1)['sharpe']:.2f})")
    print(f" JOINT_PERC real {stats(bo2)['sharpe']:.2f} vs V2_BOOK {stats(bo1)['sharpe']:.2f}")

if __name__ == "__main__":
    main()
