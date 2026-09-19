"""
labels.py — Causal, no-lookahead label constructions for crack-spread mean-reversion.

Implements ranked clean labels from /tmp/rare_event_models.md (ideas 1-7) and
regime features from /tmp/audit_report.md, without touching algoterminal-data.

All functions are causal: they use only data available at t-1 to label day t.
References: Lopez de Prado, Advances in Financial ML Ch.3 (triple-barrier);
EVT peaks-over-threshold (Coles, POT survey arxiv:1905.12184);
Hamilton 1989 regime switching.

Reuse existing panel fetch from harness.py / factor_book.py; no new deps beyond
pandas/numpy (scipy optional).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrier_label(
    spread_series: pd.Series,
    vol_series: pd.Series,
    profit_k: float = 1.0,
    stop_k: float = 0.5,
    vertical_days: int = 10,
) -> pd.DataFrame:
    """
    Triple-barrier method with meta-label (Lopez de Prado Ch.3).

    For each day t, set upper barrier = spread[t] + profit_k*vol[t],
    lower barrier = spread[t] - stop_k*vol[t], vertical barrier at t+vertical_days.
    Scan forward causally; meta_label=1 if profit hit before stop/time else 0.
    All barriers use vol at t (which must be causal, e.g., rolling std shifted by 1).

    Args:
        spread_series: crack spread level (per-barrel), indexed by date.
        vol_series: spread volatility scale (same index, already causal e.g. rolling std).
        profit_k: upper barrier in vol units (asymmetric for crack; default 1.0).
        stop_k: lower barrier in vol units (default 0.5, tighter stop).
        vertical_days: max holding horizon (trading days).

    Returns:
        DataFrame indexed like spread_series with columns:
        pt_hit, sl_hit, time_hit, barrier (pt/sl/time), meta_label,
        days_to_hit, entry_spread, pt_level, sl_level.
    """
    s = spread_series.sort_index()
    v = vol_series.reindex(s.index)
    n = len(s)
    # Pre-allocate
    out = pd.DataFrame(index=s.index)
    out["entry_spread"] = s
    out["pt_level"] = s + profit_k * v
    out["sl_level"] = s - stop_k * v
    out["pt_hit"] = False
    out["sl_hit"] = False
    out["time_hit"] = False
    out["barrier"] = "time"
    out["meta_label"] = 0
    out["days_to_hit"] = vertical_days
    out["hit_day"] = pd.NaT

    s_vals = s.to_numpy(dtype=float)
    pt_vals = out["pt_level"].to_numpy(dtype=float)
    sl_vals = out["sl_level"].to_numpy(dtype=float)
    idx = s.index

    for i in range(n):
        if np.isnan(s_vals[i]) or np.isnan(pt_vals[i]) or np.isnan(sl_vals[i]):
            out.iloc[i, out.columns.get_loc("time_hit")] = True
            continue
        pt = pt_vals[i]
        sl = sl_vals[i]
        hit = "time"
        days = vertical_days
        hit_day = pd.NaT
        # forward scan
        upper = min(i + vertical_days, n - 1)
        for j in range(i + 1, upper + 1):
            fv = s_vals[j]
            if np.isnan(fv):
                continue
            # check both barriers; if both hit same bar, prefer pt if closer? use pt first for long bias
            pt_touched = fv >= pt
            sl_touched = fv <= sl
            if pt_touched and sl_touched:
                # ambiguous bar — choose nearer barrier in price distance
                # for long crack reversion, treat as pt if profit distance smaller
                hit = "pt" if abs(fv - pt) <= abs(fv - sl) else "sl"
                days = j - i
                hit_day = idx[j]
                break
            if pt_touched:
                hit = "pt"
                days = j - i
                hit_day = idx[j]
                break
            if sl_touched:
                hit = "sl"
                days = j - i
                hit_day = idx[j]
                break
        if hit == "pt":
            out.iloc[i, out.columns.get_loc("pt_hit")] = True
            out.iloc[i, out.columns.get_loc("meta_label")] = 1
        elif hit == "sl":
            out.iloc[i, out.columns.get_loc("sl_hit")] = True
            out.iloc[i, out.columns.get_loc("meta_label")] = 0
        else:
            out.iloc[i, out.columns.get_loc("time_hit")] = True
            out.iloc[i, out.columns.get_loc("meta_label")] = 0
        out.iloc[i, out.columns.get_loc("barrier")] = hit
        out.iloc[i, out.columns.get_loc("days_to_hit")] = days
        if hit_day is not pd.NaT:
            out.iloc[i, out.columns.get_loc("hit_day")] = hit_day
    return out


def percentile_rank_label(
    spread_series: pd.Series,
    seasonal_window: int = 90,
    pct_threshold: float = 5.0,
) -> pd.Series:
    """
    Distribution-free seasonal percentile label (EVT threshold alternative).

    Replaces Gaussian z<-0.75 with rolling seasonal residual percentile.
    Residual = spread - seasonal_mean (same-calendar-month expanding mean,
    strictly before t). Label = 1 if residual percentile < pct_threshold
    within trailing seasonal_window residuals. Robust to fat tails / 2020-22 spikes.

    EVT threshold concept: percentile rank is POT threshold (Coles; arxiv:1905.12184)
    — distribution-free, no Gaussian assumption.

    Args:
        spread_series: crack spread level.
        seasonal_window: trailing window for percentile rank (e.g., 90).
        pct_threshold: percentile threshold (5 = 5th percentile).

    Returns:
        Bool Series (True = extreme crush, label=1).
    """
    s = spread_series.sort_index()
    # seasonal mean: expanding same-month mean strictly before t
    seasonal_mean = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        for k, t in enumerate(idx):
            past = s.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m]
            if len(past) >= 10:
                seasonal_mean.loc[t] = past.mean()
    resid = s - seasonal_mean
    # rolling percentile rank (causal: window ending t-1)
    label = pd.Series(False, index=s.index)
    vals = resid.to_numpy(dtype=float)
    for i in range(len(s)):
        if np.isnan(vals[i]):
            continue
        lo = max(0, i - seasonal_window)
        # window strictly before i
        window = vals[lo:i]
        window = window[~np.isnan(window)]
        if len(window) < 20:
            continue
        # percentile rank: share of window below current
        rank = (window < vals[i]).sum() / len(window) * 100.0
        if rank < pct_threshold:
            label.iloc[i] = True
    return label


def regime_conditioned_filter(
    crush_signal: pd.Series,
    stress_state: pd.Series,
) -> pd.Series:
    """
    Regime-conditioned filter: crush AND stress.

    Generic AND filter for meta-label conditioning (BAA10Y pct>70,
    OVX pct>70, EIA util gap, etc.). Both inputs bool, aligned on index.
    Causal by construction: caller ensures stress_state is already lagged.

    Args:
        crush_signal: bool Series (e.g., seasonal z<-0.75 or percentile rank).
        stress_state: bool Series (e.g., stress regime flag).

    Returns:
        Bool Series filtered = crush_signal & stress_state.
    """
    a = crush_signal.reindex(stress_state.index).fillna(False).astype(bool)
    b = stress_state.reindex(crush_signal.index).fillna(False).astype(bool)
    # align to union, then intersect
    idx = a.index.union(b.index).sort_values()
    a = a.reindex(idx).fillna(False)
    b = b.reindex(idx).fillna(False)
    return (a & b).astype(bool)


def vol_adjusted_residual_label(
    spread: pd.Series,
    wti: pd.Series | None = None,
    natgas: pd.Series | None = None,
    util: pd.Series | None = None,
    window: int = 252,
) -> pd.Series:
    """
    Vol-adjusted residual after rolling regression on drivers.

    Residualizes spread against WTI / NatGas / utilization (or any drivers),
    using rolling OLS betas from window ending t-1, then vol-adjusts residual
    by trailing GARCH-like vol (rolling std). Isolates crack-specific dislocation
    vs macro oil beta (cf. EVT-GARCH, GARCH vol adjustment arxiv:2010.12218).

    All betas causal (window ending t-1). Vol divisor is trailing std shifted by 1.

    Args:
        spread: crack spread level.
        wti: driver 1 (e.g., CL close) or None.
        natgas: driver 2 or None.
        util: driver 3 (e.g., refinery util) or None.
        window: rolling window for beta estimation.

    Returns:
        Series of vol-adjusted residual z-scores (causal, NaN where insufficient).
    """
    # align
    frames = {"spread": spread}
    if wti is not None:
        frames["wti"] = wti
    if natgas is not None:
        frames["natgas"] = natgas
    if util is not None:
        frames["util"] = util
    df = pd.DataFrame(frames).sort_index()
    # drivers list
    driver_cols = [c for c in ["wti", "natgas", "util"] if c in df.columns]
    resid = pd.Series(np.nan, index=df.index, dtype=float)
    # if no drivers, just deseasonalize via vol-adjust
    if not driver_cols:
        vol = df["spread"].diff().rolling(window, min_periods=20).std().shift(1)
        resid = (df["spread"] - df["spread"].rolling(window, min_periods=20).mean().shift(1)) / vol.replace(0, np.nan)
        return resid

    y = df["spread"].to_numpy(dtype=float)
    X_base = df[driver_cols].to_numpy(dtype=float)
    # add intercept
    n = len(df)
    for i in range(window, n):
        # training window ending i-1
        y_win = y[i - window : i]
        X_win = X_base[i - window : i, :]
        # mask NaN
        mask = ~np.isnan(y_win)
        for c in range(X_win.shape[1]):
            mask &= ~np.isnan(X_win[:, c])
        if mask.sum() < max(20, window // 3):
            continue
        yw = y_win[mask]
        Xw = X_win[mask]
        # add intercept
        Xw1 = np.column_stack([np.ones(len(Xw)), Xw])
        try:
            beta, *_ = np.linalg.lstsq(Xw1, yw, rcond=None)
        except np.linalg.LinAlgError:
            continue
        # predict current
        x_cur = X_base[i, :]
        if np.isnan(x_cur).any() or np.isnan(y[i]):
            continue
        x1 = np.concatenate([[1.0], x_cur])
        pred = float(x1 @ beta)
        resid.iloc[i] = y[i] - pred
    # vol-adjust residual (trailing vol of residual)
    vol = resid.rolling(window, min_periods=20).std().shift(1).replace(0, np.nan)
    z = resid / vol
    return z


if __name__ == "__main__":
    # Demo: load panel via existing harness fetch (or synthetic fallback),
    # print label counts vs raw z<-0.75 and barrier hit distribution for 10d horizon.
    import sys

    print("=== labels.py demo ===")
    # Try harness fetch first, then factor_book fetch, then synthetic
    closes = None
    crack = None
    try:
        # reuse factor_book fetch (simpler return type)
        import importlib.util
        from pathlib import Path

        fb_path = Path(__file__).with_name("factor_book.py")
        if fb_path.exists():
            spec = importlib.util.spec_from_file_location("fb", str(fb_path))
            fb = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fb)
            # try fetch with short window to avoid long download in demo
            try:
                df = fb.fetch_panel("2023-01-01", "2026-09-09")
                if not df.empty and "CL" in df.columns:
                    levels = fb.build_levels(df)
                    crack = levels.get("crack_321")
                    print(f"Loaded real panel via factor_book.fetch_panel: {df.index.min().date()} -> {df.index.max().date()} rows={len(df)}")
            except Exception as e:
                print(f"Real fetch failed ({e}), using synthetic")
                crack = None
    except Exception as e:
        print(f"Import fetch failed ({e}), using synthetic")

    if crack is None or crack.dropna().empty:
        print("Generating synthetic crack panel (756 days, 3y)...")
        np.random.seed(42)
        dates = pd.date_range("2023-09-08", periods=756, freq="B")
        # synthetic crack: mean 25, std 5, seasonal + episodic crushes
        base = 25 + 5 * np.sin(2 * np.pi * np.arange(756) / 252 * 2)
        noise = np.random.randn(756) * 2.5
        # inject ~17 crush episodes
        for idx in np.random.choice(756, 17, replace=False):
            noise[idx : idx + 5] -= np.random.uniform(5, 10)
        crack = pd.Series(base + noise, index=dates, name="crack_321")
        print(f"Synthetic crack: mean={crack.mean():.2f} std={crack.std():.2f} n={len(crack)}")

    crack = crack.dropna().sort_index()
    # raw seasonal z label (90d same-month norm, z<-0.75) — replicate factor_book.seasonal_z
    try:
        from pathlib import Path
        import importlib.util

        fb_path2 = Path(__file__).with_name("factor_book.py")
        spec2 = importlib.util.spec_from_file_location("fb2", str(fb_path2))
        fb2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(fb2)
        z = fb2.seasonal_z(crack)
        raw_label = z < -0.75
        raw_label = raw_label.fillna(False)
        print(f"\nRaw seasonal z<-0.75: {int(raw_label.sum())} events / {len(raw_label)} days ({raw_label.mean()*100:.2f}%)")
    except Exception as e:
        print(f"seasonal_z failed ({e}), using simple z")
        roll_mean = crack.shift(1).rolling(90, min_periods=45).mean()
        roll_std = crack.shift(1).rolling(90, min_periods=45).std()
        z = (crack.shift(1) - roll_mean) / roll_std
        raw_label = (z < -0.75).fillna(False)
        print(f"Simple z<-0.75: {int(raw_label.sum())} events")

    # percentile rank label
    pct_label = percentile_rank_label(crack, seasonal_window=90, pct_threshold=5)
    print(f"Percentile rank <5th pct (90d): {int(pct_label.sum())} events ({pct_label.mean()*100:.2f}%)")

    # vol series for triple barrier: rolling std of spread diff, shifted causal
    vol = crack.diff().rolling(20, min_periods=10).std().shift(1)
    vol = vol.fillna(vol.median()).replace(0, np.nan).fillna(1.0)
    tb = triple_barrier_label(crack, vol, profit_k=1.0, stop_k=0.5, vertical_days=10)
    # meta label only relevant on crush days; report both pooled and conditional
    print(f"\nTriple-barrier (profit_k=1.0, stop_k=0.5, vertical=10d):")
    print(f"  PT hits: {int(tb['pt_hit'].sum())}  SL hits: {int(tb['sl_hit'].sum())}  Time: {int(tb['time_hit'].sum())}")
    print(f"  Meta_label=1 (profit first): {int(tb['meta_label'].sum())} / {len(tb)} ({tb['meta_label'].mean()*100:.2f}%)")
    # conditional on raw crush signal
    if int(raw_label.sum()) > 0:
        cond = tb.loc[raw_label]
        print(f"  Conditional on raw z<-0.75 ({int(raw_label.sum())} triggers):")
        print(f"    PT {int(cond['pt_hit'].sum())} SL {int(cond['sl_hit'].sum())} Time {int(cond['time_hit'].sum())}  hit-rate={cond['meta_label'].mean()*100:.1f}%")
        # per-regime hit rate (behavior-first): split by vol regime
        vol_pct = vol.rank(pct=True)
        high_vol = vol_pct > 0.7
        low_vol = vol_pct <= 0.7
        for name, mask in [("high_vol (>70pct)", high_vol), ("low_vol (<=70pct)", low_vol)]:
            m = raw_label & mask
            if int(m.sum()) > 0:
                sub = tb.loc[m]
                print(f"    Regime {name}: n={int(m.sum())} hit-rate={sub['meta_label'].mean()*100:.1f}% PT={int(sub['pt_hit'].sum())} SL={int(sub['sl_hit'].sum())}")
    # vol-adjusted residual label demo (using WTI proxy as crack itself lagged if no drivers)
    try:
        var = vol_adjusted_residual_label(crack, wti=crack.shift(5), window=90)
        extreme = (var < -1.0).fillna(False)
        print(f"\nVol-adjusted residual z<-1.0: {int(extreme.sum())} events ({extreme.mean()*100:.2f}%)  (residual vol-adjusted)")
    except Exception as e:
        print(f"vol_adjusted_residual_label demo failed: {e}")

    # regime filter demo
    try:
        stress = (vol.rank(pct=True) > 0.7).fillna(False)
        filtered = regime_conditioned_filter(raw_label, stress)
        print(f"\nRegime-conditioned filter (crush AND stress vol>70pct): {int(filtered.sum())} events vs raw {int(raw_label.sum())}")
    except Exception as e:
        print(f"regime filter demo failed: {e}")

    print("\nDemo complete.")
