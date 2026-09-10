"""Track A — Incremental CORE3 upgrade (Round 10A).

Minimal price-only (+ Cushing already wired) upgrade. All thresholds
pre-registered round numbers. Grid small, reported fully.

Owns:
  - probationary JOINT (forces FULL for N days then reverts to V2 unless still JOINT; N=3,5,10)
  - Cushing utilization sizing for bzwti (z-based continuous scale, not binary gate; min_scale 0.5/0.7)
  - gap cap variant (NOCAP / CAP8 / CAP5)
  - per-complex DD overlay option (book-level vs per-complex hysteresis)

Costs 5bps/20roll, causal at close t-1, windows IS 2023-09-08+, OOS 2007-07-30..2023-09-08, warmup 90.
Imports factor_book.py (fb) and book_oos_v4/v5 engines (b4/b5). No new API keys.
Cushing: uses cached EIA parquet if present, else skips gracefully (CUSH OFF).
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

# --- load engines ---
spec_fb = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec_fb)
spec_fb.loader.exec_module(fb)

spec_b4 = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec_b4)
spec_b4.loader.exec_module(b4)

spec_b5 = importlib.util.spec_from_file_location("b5", str(DEV / "book_oos_v5.py"))
b5 = importlib.util.module_from_spec(spec_b5)
spec_b5.loader.exec_module(b5)

SUBSET = ["crack_321", "cross_sectional", "bzwti"]
COMPLEXES = {"crack": ["crack_321", "cross_sectional"], "bzwti": ["bzwti"]}

# joint pre-registered thresholds (round, from Round 9)
THR_CRASH = 1.0
THR_DEPTH = -1.25
THR_CRUDE = -0.15

# Cushing scaling pre-registered: scale z where z = same-month expanding z (weekly, lag 6d, ffill)
# scale = 1 - (1-min_scale)*clip((z - 0)/1.5, 0, 1). So 0->1.0, 1.5->min_scale.
CUSH_Z0 = 0.0
CUSH_Z1 = 1.5

CAPS = {"NOCAP": None, "CAP8": 0.08, "CAP5": 0.05}


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "worst": np.nan, "vol": np.nan,
                "mean": np.nan, "skew": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "sharpe": r.mean() / r.std() * np.sqrt(252),
            "maxdd": (eq / eq.cummax() - 1).min(), "worst": r.min(), "vol": r.std() * np.sqrt(252),
            "mean": r.mean(), "skew": r.skew()}


def window(s, start, end):
    out = s.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out


def window_df(df, start, end):
    out = df.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out


def get_cushing_daily(index: pd.Index) -> pd.Series | None:
    """Load Cushing weekly stocks, build same-month z, lag 6d, forward-fill to daily. Returns None if no cache."""
    # try parquet cache first, then /tmp csvs
    for p in [Path("/home/sebas/.algoterminal-data/cache/eia__W_EPC0_SAX_YCUOK_MBBL.parquet"),
              Path("/tmp/eia_W_EPC0_SAX_YCUOK_MBBL.csv")]:
        if p.exists():
            try:
                if p.suffix == ".parquet":
                    df = pd.read_parquet(p)
                    # eia cache has column 'close' index date
                    s = df["close"].dropna() if "close" in df.columns else df.iloc[:, 0].dropna()
                    s.index = pd.to_datetime(s.index)
                else:
                    df = pd.read_csv(p, index_col=0, parse_dates=True)
                    s = df["close"].dropna()
                # weekly same-month z (expanding, min 12 obs)
                z = pd.Series(np.nan, index=s.index, dtype=float)
                for m in range(1, 13):
                    idx = s.index[s.index.month == m]
                    for i in range(len(idx)):
                        t = idx[i]
                        past = s.loc[: t - pd.Timedelta(days=1)]
                        past = past[past.index.month == m].dropna()
                        if len(past) >= 12:
                            mu, sd = past.mean(), past.std()
                            if sd > 1e-9:
                                z.loc[t] = (s.loc[t] - mu) / sd
                z = z.clip(-8, 8)
                z.index = z.index + pd.Timedelta(days=6)  # report lag
                z = z.sort_index()
                daily = z.reindex(index.union(z.index)).sort_index().ffill().reindex(index)
                return daily
            except Exception as e:
                print(f"WARN Cushing load {p}: {e}")
                return None
    return None


def cushing_scale(z_daily: pd.Series, min_scale: float) -> pd.Series:
    """Continuous scale 1.0 -> min_scale over z in [0, 1.5]."""
    sc = 1.0 - (1.0 - min_scale) * ((z_daily - CUSH_Z0) / (CUSH_Z1 - CUSH_Z0)).clip(0, 1)
    return sc.fillna(1.0).clip(min_scale, 1.0)


def joint_signal(depth: pd.Series, crash5: pd.Series, crude20: pd.Series) -> pd.Series:
    h = depth.shift(1)
    c = (depth.shift(6) - depth.shift(1))
    cr = crude20.shift(1) if crude20 is not None else pd.Series(np.nan, index=depth.index)
    # crude20 already shift(1) before passing? caller passes raw pct_change, so shift here
    # depth and crash already incorporate shift(1) logic; keep consistent with book_oos_v7
    # book_oos_v7: held=depth.shift(1), crash5=depth.shift(6)-depth.shift(1), crude20=df.CL.pct_change(20).shift(1)
    # then joint_signal uses those shifted series directly without extra shift.
    # To avoid double-shift, we expect caller passes already-shifted series.
    # This wrapper is not used directly; main builds joint as (crash5>=thr & depth_shifted<=thr & crude20_shifted<=thr)
    raise NotImplementedError


def apply_overlay_book(book: pd.Series, vstate: pd.Series | None, vol_target=0.10, cut=-0.06, halt=-0.10,
                       prob_n: int | None = None) -> pd.Series:
    """Book-level overlay with optional probationary JOINT.

    vstate: bool series (causal, True at day t means force FULL at open t).
    prob_n: if None -> JOINT forces FULL only while true (indefinite while true).
            if int -> JOINT triggers a probationary FULL window of N days; after expiry
                       reverts to v2 unless still JOINT (which retriggers).
    """
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    if vstate is not None:
        vv = vstate.reindex(book.index).fillna(False).to_numpy(dtype=bool)
    else:
        vv = np.zeros(n, dtype=bool)
    prob_remain = 0
    for t in range(n):
        # probationary countdown overrides?
        if prob_n is not None and prob_remain > 0:
            scale[t] = 1.0
            prob_remain -= 1
        else:
            scale[t] = state
        r = float(book.iloc[t])
        ret = r * float(g.iloc[t]) * scale[t]
        eq *= 1.0 + ret
        hwm = max(hwm, eq)
        exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        new_high = eng_eq >= was_hwm
        # check JOINT trigger for next day's state
        is_joint = bool(vv[t])
        if prob_n is not None:
            if is_joint and prob_remain == 0:
                # start probation for NEXT day? But we already applied today.
                # Instead, set prob_remain for next t: force scale=1 for next prob_n days
                # Need to decide: joint at close t forces FULL at open t+1.
                # So today's vv[t] already forced today's scale if prob active.
                # For prob logic, we check next day's forcing via prob_remain.
                # Simpler: if joint today, set prob_remain = prob_n (will cover next N days)
                # But today was already handled via prob_remain from prior trigger.
                # To make joint immediate, also set state=1.0.
                prob_remain = prob_n
                state = 1.0
            # v2 transitions only when not in probation
            if prob_remain == 0:
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
                else:
                    if new_high:
                        state = 1.0
        else:
            # non-probationary: joint forces FULL immediately (overrides)
            if is_joint:
                state = 1.0
            elif state == 1.0:
                if exp_dd <= halt:
                    state = 0.0
                elif exp_dd <= cut:
                    state = 0.5
            elif state == 0.5:
                if exp_dd <= halt:
                    state = 0.0
                elif new_high:
                    state = 1.0
            else:
                if new_high:
                    state = 1.0
    return book * pd.Series(scale, index=book.index) * g


def apply_overlay_book_prob_causal(book: pd.Series, joint_raw: pd.Series | None, prob_n: int | None,
                                   vol_target=0.10, cut=-0.06, halt=-0.10) -> pd.Series:
    """Book-level overlay with probationary JOINT, mirroring b4.apply_overlay v2.

    Causal: joint_raw[t] true (signal at close t-1) forces FULL at open t.
    prob_n=None: joint forces FULL while true (next-day state logic mirrors b7 off-by-one for comparability,
                but we make it causal: joint today -> scale today=1).
    prob_n=int: joint triggers N-day probation (timer). While timer>0 scale=1. Retrigger extends.
    v2 ladder otherwise: if eng new high -> 1.0 else if exp_dd <= halt ->0.0 else if exp_dd <=cut ->0.5
    Matches b4 priority: new_high first.
    """
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    if joint_raw is None:
        jv = np.zeros(n, dtype=bool)
    else:
        jv = joint_raw.reindex(book.index).fillna(False).to_numpy(dtype=bool)
    timer = 0
    for t in range(n):
        # joint trigger at close t-1 for day t
        if jv[t] and prob_n is not None:
            timer = prob_n
        # decide scale for day t
        if prob_n is not None and timer > 0:
            scale[t] = 1.0
            timer -= 1
            r = float(book.iloc[t])
            ret = r * float(g.iloc[t]) * scale[t]
            eq *= 1.0 + ret
            hwm = max(hwm, eq)
            eng_eq *= 1.0 + r
            eng_hwm = max(eng_hwm, eng_eq)
            state = 1.0
            continue
        if prob_n is None and jv[t]:
            scale[t] = 1.0
            r = float(book.iloc[t])
            ret = r * float(g.iloc[t]) * scale[t]
            eq *= 1.0 + ret
            hwm = max(hwm, eq)
            eng_eq *= 1.0 + r
            was_hwm = eng_hwm
            eng_hwm = max(eng_hwm, eng_eq)
            state = 1.0
            continue
        scale[t] = state
        r = float(book.iloc[t])
        ret = r * float(g.iloc[t]) * scale[t]
        eq *= 1.0 + ret
        hwm = max(hwm, eq)
        exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        new_high = eng_eq >= was_hwm
        # b4 priority: new_high first, then halt, then cut
        if new_high:
            state = 1.0
        elif exp_dd <= halt:
            state = 0.0
        elif exp_dd <= cut:
            state = 0.5
    return book * pd.Series(scale, index=book.index) * g


def apply_overlay_per_complex(net: pd.DataFrame, subset: list[str], weights: dict[str, float],
                              joint_raw: pd.Series | None, prob_n: int | None,
                              vol_target=0.10, cut=-0.06, halt=-0.10) -> pd.Series:
    """Per-complex overlay: each complex has its own DD ladder and prob timer."""
    # build complex returns
    # weight book is EQ across factors; per-complex keeps those weights but applies gear per complex
    # For CORE3: crack complex has 2 factors, bzwti has 1. Keep factor weights within book.
    # Apply overlay per complex on its weighted return, then sum.
    out = pd.Series(0.0, index=net.index)
    for cname, legs in COMPLEXES.items():
        c_legs = [f for f in legs if f in subset]
        if not c_legs:
            continue
        c_w = {f: weights[f] for f in c_legs}
        # complex raw return (weighted sum of factor nets, before overlay)
        c_ret = pd.Series(0.0, index=net.index)
        for f in c_legs:
            c_ret = c_ret + c_w[f] * net[f]
        # apply probationary overlay to this complex
        c_over = apply_overlay_book_prob_causal(c_ret, joint_raw, prob_n, vol_target, cut, halt)
        out = out + c_over
    return out


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    levels["__df__"] = df
    print(f"Window: {df.index.min().date()} -> {df.index.max().date()} rows={len(df)}")

    # causal features for joint
    # depth = most-crushed held leg z through t-1
    # Need leg positions for depth; build once with NOCAP baseline
    # Depth is independent of cap/scale but we recompute per cap variant inside loop if needed.
    # For joint signal we use NOCAP depth (stable across caps).
    zdf = {}
    for leg in ["crack_321", "crack_gas", "crack_ho", "ng", "bzwti"]:
        zdf[leg] = fb.seasonal_z(levels[leg])
    for leg in ["brent321", "brent_gas", "brent_ho"]:
        try:
            zdf[leg] = fb.seasonal_z(b5.brent_levels(df)[leg])
        except Exception:
            pass

    # Cushing daily z
    cush_daily = get_cushing_daily(df.index)
    if cush_daily is not None:
        print(f"Cushing cache OK: z range {cush_daily.min():.2f}..{cush_daily.max():.2f} non-na {(~cush_daily.isna()).sum()}")
    else:
        print("Cushing cache MISSING: CUSH dimension will be OFF only (graceful skip).")

    # Precompute depth baseline (NOCAP)
    factors0, rets0, turn0, legpos0 = b5.build_v5(levels, None, False)
    depth0 = b5.book_depth(legpos0, zdf, pd.Index(df.index))
    held0 = depth0.shift(1)
    crash5_0 = depth0.shift(6) - depth0.shift(1)
    crude20_raw = df["CL"].pct_change(20).shift(1)
    joint_raw0 = (crash5_0 >= THR_CRASH) & (held0 <= THR_DEPTH) & (crude20_raw <= THR_CRUDE)
    joint_raw0 = joint_raw0.fillna(False)
    print(f"Joint baseline (NOCAP depth) OOS joint days {(joint_raw0.loc[OOS_START:IS_START]).sum()} IS {(joint_raw0.loc[IS_START:]).sum()}")

    # grid
    cap_list = ["NOCAP", "CAP8", "CAP5"]
    # Cushing options: OFF, S05 (min 0.5), S07 (min 0.7)
    cush_opts = [("OFF", None)]
    if cush_daily is not None:
        cush_opts = [("OFF", None), ("S05", 0.5), ("S07", 0.7)]
    joint_opts = [("V2", None, None), ("J_FULL", joint_raw0, None), ("J_P3", joint_raw0, 3), ("J_P5", joint_raw0, 5), ("J_P10", joint_raw0, 10)]
    overlay_opts = ["BOOK", "PER"]

    results = []
    for capname in cap_list:
        capv = CAPS[capname]
        # rebuild engine for this cap (depth may shift slightly; joint should use cap-specific depth)
        factors, rets, turn, legpos = b5.build_v5(levels, capv, False)
        # depth for this cap
        depth = b5.book_depth(legpos, zdf, pd.Index(df.index))
        held = depth.shift(1)
        crash5 = depth.shift(6) - depth.shift(1)
        joint_raw = (crash5 >= THR_CRASH) & (held <= THR_DEPTH) & (crude20_raw <= THR_CRUDE)
        joint_raw = joint_raw.fillna(False)
        net0 = b5.apply_costs(factors, rets, turnover=turn)
        isw_df = window_df(net0, IS_START, df.index.max())
        oos_df = window_df(net0, OOS_START, IS_START)
        w = b5.weight_scheme(isw_df[SUBSET], "EQ")

        for cush_label, cush_min in cush_opts:
            # apply Cushing scaling to bzwti net (position scaled -> return scaled)
            # Scaling is causal: scale factor at t-1 multiplies bzwti return at t.
            net = net0.copy()
            if cush_min is not None and cush_daily is not None:
                sc = cushing_scale(cush_daily, cush_min)
                # scale factor for day t is sc.shift(1) (decided at close t-1)
                sc_lag = sc.shift(1).fillna(1.0).reindex(net.index).fillna(1.0)
                # Apply scaling to bzwti factor: scale both position and return.
                # We have net already; to mimic position scaling, we scale the net return series.
                # More precise: we would rebuild bzwti position scaled, but return scaling is equivalent
                # for the book because net = scaled_pos * ret; scaling net by sc_lag approximates.
                # For causal correctness, also adjust turnover cost proportionally: net cost already in net0,
                # scaling reduces turnover too, so simple scaling of net is conservative.
                net["bzwti"] = net["bzwti"] * sc_lag
                # need to keep isw/oos slices updated
                isw_df_s = window_df(net, IS_START, df.index.max())
                oos_df_s = window_df(net, OOS_START, IS_START)
            else:
                isw_df_s = isw_df
                oos_df_s = oos_df

            for jlabel, jraw, prob_n in joint_opts:
                # select joint_raw for this cap
                j = joint_raw if jraw is not None else None
                # if j is from baseline vs cap-specific: use cap-specific joint
                if j is not None:
                    # j is already cap-specific joint_raw if we set j=joint_raw
                    if jraw is joint_raw0:
                        j = joint_raw  # use cap-specific
                    else:
                        j = joint_raw

                for ov in overlay_opts:
                    # build book returns (pre-overlay) for IS/OOS slices will be handled inside overlay call
                    # For BOOK overlay: weighted book then overlay
                    # For PER overlay: overlay per complex then sum
                    for win_label, win_df in [("IS", isw_df_s), ("OOS", oos_df_s)]:
                        pass  # placeholder

                    # Build full book series then window
                    # full net -> book returns (EQ) -> full book series
                    # Then apply overlay on windowed book
                    # But per-complex overlay needs net + weights

                    # Build book-level raw book (pre-overlay) full series
                    raw_book = b5.book_returns(net, SUBSET, w)

                    raw_is = window(raw_book, IS_START, df.index.max())
                    raw_oos = window(raw_book, OOS_START, IS_START)

                    # joint slices
                    if j is not None:
                        j_is = j.reindex(raw_is.index).fillna(False)
                        j_oos = j.reindex(raw_oos.index).fillna(False)
                    else:
                        j_is = pd.Series(False, index=raw_is.index)
                        j_oos = pd.Series(False, index=raw_oos.index)

                    if ov == "BOOK":
                        over_is = apply_overlay_book_prob_causal(raw_is, j_is, prob_n)
                        over_oos = apply_overlay_book_prob_causal(raw_oos, j_oos, prob_n)
                    else:
                        # per-complex needs net slices
                        j_is_pc = j_is
                        j_oos_pc = j_oos
                        over_is = apply_overlay_per_complex(
                            net.reindex(raw_is.index), SUBSET, w, j_is_pc, prob_n)
                        over_oos = apply_overlay_per_complex(
                            net.reindex(raw_oos.index), SUBSET, w, j_oos_pc, prob_n)
                        # re-window (per-complex returns may have warmup already via net window; ensure same window)
                        over_is = window(over_is, IS_START, df.index.max())
                        over_oos = window(over_oos, OOS_START, IS_START)

                    si = stats(over_is)
                    so = stats(over_oos)
                    results.append({
                        "cap": capname, "cush": cush_label, "joint": jlabel, "prob_n": prob_n if prob_n else 0,
                        "overlay": ov,
                        "IS_sh": si["sharpe"], "IS_cagr": si["cagr"], "IS_dd": si["maxdd"], "IS_vol": si["vol"], "IS_worst": si["worst"],
                        "OOS_sh": so["sharpe"], "OOS_cagr": so["cagr"], "OOS_dd": so["maxdd"], "OOS_vol": so["vol"], "OOS_worst": so["worst"],
                    })

    res = pd.DataFrame(results)
    res.to_csv(DEV / "book_oos_v8_A_results.csv", index=False)
    print(f"\nSaved book_oos_v8_A_results.csv ({len(res)} rows)")

    # summary prints
    print("\n=== Baseline (V2) vs best probationary ===")
    base = res[(res.joint == "V2") & (res.overlay == "BOOK") & (res.cush == "OFF")]
    for _, r in base.iterrows():
        print(f" {r['cap']:5s} BOOK V2 OFF | IS {r['IS_sh']:.2f} DD {r['IS_dd']*100:+.1f}% | OOS {r['OOS_sh']:.2f} CAGR {r['OOS_cagr']*100:.2f}% DD {r['OOS_dd']*100:+.1f}% vol {r['OOS_vol']*100:.1f}% worst {r['OOS_worst']*100:+.2f}%")
    # best by Sharpe+convexity tradeoff: maximize Sharpe with DD constraint -13.5%
    filt = res[res.OOS_dd >= -0.135]
    best = filt.sort_values(["OOS_sh", "OOS_cagr"], ascending=False).head(10)
    print("\n=== Top 10 by OOS Sharpe (DD>=-13.5%) ===")
    for _, r in best.iterrows():
        print(f" {r['cap']:5s} {r['cush']:3s} {r['joint']:6s} {r['overlay']:4s} | IS {r['IS_sh']:.2f} DD {r['IS_dd']*100:+.1f}% | OOS {r['OOS_sh']:.2f} CAGR {r['OOS_cagr']*100:.2f}% DD {r['OOS_dd']*100:+.1f}% vol {r['OOS_vol']*100:.1f}% worst {r['OOS_worst']*100:+.2f}%")
    # per-complex comparison
    print("\n=== Per-complex vs BOOK (same cap/cush/joint) ===")
    for cap in cap_list:
        for cush_l in [x[0] for x in cush_opts][:2]:
            for j in ["V2", "J_P5", "J_P10"]:
                b = res[(res.cap == cap) & (res.cush == cush_l) & (res.joint == j) & (res.overlay == "BOOK")]
                p = res[(res.cap == cap) & (res.cush == cush_l) & (res.joint == j) & (res.overlay == "PER")]
                if len(b) and len(p):
                    br, pr = b.iloc[0], p.iloc[0]
                    print(f" {cap:5s} {cush_l:3s} {j:5s} BOOK {br['OOS_sh']:.2f}/{br['OOS_dd']*100:+.1f}% vs PER {pr['OOS_sh']:.2f}/{pr['OOS_dd']*100:+.1f}%")

    # verify run
    print("\n=== Verify IS vs OOS for champion candidate (largest Sharpe under -12% DD) ===")
    champ = res[res.OOS_dd >= -0.12].sort_values("OOS_sh", ascending=False).head(1)
    if len(champ):
        print(champ.to_string(index=False))
    else:
        print("No candidate under -12% DD; showing best overall")
        print(res.sort_values("OOS_sh", ascending=False).head(1).to_string(index=False))

    print("\nDONE")

if __name__ == "__main__":
    main()
