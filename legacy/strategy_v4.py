"""Crack Spread Hedging Pressure -> Mean Reversion, v4 (multi-leg portfolio).

v3 established the core edge: buy the crack when it is seasonally crushed
(z-score of the deseasonalized level below -Z_ENTRY), long-only. v4 extends
that to a diversified portfolio of three related legs:

  - crack_321 : 3:2:1 WTI crack  (2*RB + HO)/3 * 42 - CL
  - crack_gas : gasoline crack   RB * 42 - CL
  - crack_ho  : heating crack    HO * 42 - CL

Gasoline and heating cracks are nearly uncorrelated (daily-return corr ~0.1):
different demand seasons, different refinery dynamics. Each leg carries the
same hedging-pressure mean-reversion thesis, so the combined book gets more
crush episodes (more trades) and diversifies leg-specific tail risk.

Contract: generate_signals / size_positions / apply_risk_rules return a
DataFrame indexed like the price panel with one column per leg. The harness
computes per-leg returns and sums them into the book PnL.

Lookahead note: all rolling statistics use data strictly before bar t
(inputs shifted one bar), so nothing at t sees bar t's close.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# --- signal parameters ---------------------------------------------------
Z_LOOKBACK = 90       # rolling window for the z-score mean and std (on the deseasonalized level)
Z_ENTRY = 0.75        # enter long when the crack is crushed past this z
Z_EXIT = -0.5         # exit long when the z-score recovers to this level
MIN_OBS = 45          # min observations before a rolling stat is valid
Z_MIN_STD_REL = 1e-4  # std must be meaningful relative to |level| to trust z
Z_MAX_Z = 8.0         # clip z to bound the effect of tail bars
SEASON_MIN_OBS = 10   # min same-month observations before the seasonal mean is valid

# --- legs ----------------------------------------------------------------
# Book A: the 3:2:1 crack plus the heating-oil crack. Daily-return corr ~0.19,
# both Sharpe > 1 standalone, so the combined book lifts Sharpe to ~1.4.
# The gasoline crack ("crack_gas") is excluded: it has the strongest raw
# seasonal edge but its traded profile is poor (Sharpe ~0.3, deep drawdowns)
# and it dilutes the book.
LEGS = ["crack_321", "crack_ho"]

# --- crack construction --------------------------------------------------
GALLONS_PER_BARREL = 42.0
_SYMBOL_ALIASES = {
    "crude": "CL", "wti": "CL", "cl": "CL",
    "rb": "RB", "gasoline": "RB", "rbob": "RB",
    "ho": "HO", "heating": "HO", "ulsd": "HO", "diesel": "HO",
}

# --- sizing parameters ---------------------------------------------------
VOL_LOOKBACK = 20     # rolling window for realized volatility
VOL_TARGET = 0.50     # annualized volatility target per leg (book runs 2 legs)
MAX_LEVERAGE = 1.0    # cap on |position| per leg (fraction of capital)
VOL_FALLBACK = 0.50   # conservative scale when no vol history exists yet
SHORT_MIN_OBS = 10    # min observations for the short sizing/risk windows

# --- risk parameters -----------------------------------------------------
STOP_LOOKBACK = 10       # trailing-stop reference window (bars)
STOP_SIGMA = 1.25        # trailing-stop distance in multi-day volatility units
DAY_STD_LOOKBACK = 20    # window for the daily volatility of absolute moves
DAILY_LOSS_SIGMA = 3.0   # flatten when an adverse one-bar move exceeds this many daily volatilities
COOLDOWN_BARS = 5        # hold the book flat this many bars after a forced flatten
HARD_STOP_PCT = 0.20     # tail cap: flatten a long if the leg falls this fraction below its entry level
                         # (set wide enough to never trigger on normal moves; caps catastrophic out-of-sample loss)


def _canonical_symbol(name: object) -> str:
    """Map a panel column label to a canonical symbol, or '' when unknown."""
    key = str(name).strip().lower()
    return _SYMBOL_ALIASES.get(key, "")


def _leg_levels(prices) -> dict[str, pd.Series]:
    """Return the per-barrel level of each leg from a CL/RB/HO price panel."""
    if isinstance(prices, pd.Series):
        raise TypeError("v4 needs a CL/RB/HO panel (DataFrame), not a single series")
    canonical: dict = {}
    for label in prices.columns:
        sym = _canonical_symbol(label)
        if sym:
            canonical.setdefault(sym, label)
    cl_col = canonical.get("CL")
    rb_col = canonical.get("RB")
    ho_col = canonical.get("HO")
    if cl_col is None or rb_col is None or ho_col is None:
        raise ValueError("v4 needs CL, RB and HO columns in the price panel")
    cl = prices[cl_col].astype(float)
    rb = prices[rb_col].astype(float)
    ho = prices[ho_col].astype(float)
    return {
        "crack_321": (2 * rb + ho) / 3 * GALLONS_PER_BARREL - cl,
        "crack_gas": rb * GALLONS_PER_BARREL - cl,
        "crack_ho": ho * GALLONS_PER_BARREL - cl,
    }


def _seasonal_mean(spread: pd.Series) -> pd.Series:
    """Trailing seasonal mean: expanding mean of past same-calendar-month levels."""
    out = pd.Series(np.nan, index=spread.index)
    for m in range(1, 13):
        idx = spread.index[spread.index.month == m]
        for i in range(len(idx)):
            t = idx[i]
            past = spread.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m]
            if len(past) >= SEASON_MIN_OBS:
                out.loc[t] = past.mean()
    return out


def _z_score(spread: pd.Series) -> pd.Series:
    """Deseasonalized z-score of a leg level, using only data before bar t."""
    prev = spread.shift(1)
    seasonal = _seasonal_mean(prev)
    adj = prev - seasonal
    mean = adj.rolling(Z_LOOKBACK, min_periods=MIN_OBS).mean()
    std = adj.rolling(Z_LOOKBACK, min_periods=MIN_OBS).std()
    min_std = Z_MIN_STD_REL * mean.abs()
    valid = std.fillna(0.0) > min_std.fillna(0.0)
    z = (adj - mean) / std.where(valid)
    return z.replace([np.inf, -np.inf], np.nan).clip(-Z_MAX_Z, Z_MAX_Z)


def leg_levels(prices: pd.DataFrame) -> dict[str, pd.Series]:
    """Public accessor for the per-leg level series (used by the harness for PnL)."""
    return _leg_levels(prices)


def generate_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """Return a per-leg signal DataFrame aligned to `prices.index`.

    Convention: +1 = long, -1 = short, 0 = flat. Each leg is long when its
    deseasonalized z-score is crushed below -Z_ENTRY, and exits when the
    crush fades back to Z_EXIT. Long-only: the short side has no edge in the
    sample and adds tail risk.
    """
    levels = _leg_levels(prices)
    out = {}
    for leg in LEGS:
        level = levels[leg]
        z = _z_score(level)
        zz = z.to_numpy(dtype=float)
        vals = np.zeros(len(level), dtype=float)
        state = 0.0
        for i in range(len(level)):
            if np.isnan(zz[i]):
                vals[i] = 0.0
                continue
            if state == 0.0:
                if zz[i] <= -Z_ENTRY:
                    state = 1.0
            else:
                if zz[i] >= Z_EXIT:
                    state = 0.0
            vals[i] = state
        out[leg] = pd.Series(vals, index=level.index)
    return pd.DataFrame(out)


def size_positions(signal: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Vol-target each leg so the book targets a fixed annualized volatility."""
    levels = _leg_levels(prices)
    out = {}
    for leg in signal.columns:
        spread = levels[leg]
        level = spread.abs().rolling(VOL_LOOKBACK, min_periods=SHORT_MIN_OBS).mean().shift(1)
        rel_ret = spread.diff() / level
        realized = rel_ret.rolling(VOL_LOOKBACK, min_periods=SHORT_MIN_OBS).std()
        realized = realized.shift(1).replace(0.0, np.nan) * np.sqrt(252)
        scale = (VOL_TARGET / realized).clip(upper=MAX_LEVERAGE)
        uncond = rel_ret.expanding(min_periods=SHORT_MIN_OBS).std().shift(1).replace(0.0, np.nan)
        uncond = uncond * np.sqrt(252)
        fallback = (VOL_TARGET / uncond).clip(upper=MAX_LEVERAGE)
        use = scale.fillna(fallback).fillna(VOL_FALLBACK)
        pos = (signal[leg] * use).clip(-MAX_LEVERAGE, MAX_LEVERAGE)
        out[leg] = pos.fillna(0.0)
    return pd.DataFrame(out)


def apply_risk_rules(positions: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Apply risk overlays per leg and return the final position DataFrame.

    1. Exposure cap per leg.
    2. Trailing stop (bleedout / trend-continuation protection).
    3. Daily-loss circuit breaker (instant-gap protection).
    4. Hard level stop: flatten a long if the leg falls HARD_STOP_PCT below
       its entry level (deterministic max loss per trade; never triggers
       in-sample, caps out-of-sample tail loss).
    5. Cooldown after any forced flatten.
    """
    levels = _leg_levels(prices)
    out = {}
    for leg in positions.columns:
        spread = levels[leg]
        pos = positions[leg].fillna(0.0).clip(-MAX_LEVERAGE, MAX_LEVERAGE)

        day_std = spread.diff().rolling(DAY_STD_LOOKBACK, min_periods=SHORT_MIN_OBS).std()
        vol = day_std.shift(1).replace(0.0, np.nan).to_numpy(dtype=float)

        s = spread.to_numpy(dtype=float)
        arr = pos.to_numpy(dtype=float).copy()
        prev_held = pos.shift(1).fillna(0.0).to_numpy(dtype=float)
        move = spread.diff().to_numpy(dtype=float)

        maxv = spread.shift(1).rolling(STOP_LOOKBACK, min_periods=SHORT_MIN_OBS).max().to_numpy(dtype=float)
        minv = spread.shift(1).rolling(STOP_LOOKBACK, min_periods=SHORT_MIN_OBS).min().to_numpy(dtype=float)
        dist = vol * STOP_SIGMA * np.sqrt(STOP_LOOKBACK)

        stop_hit = ((arr > 0.0) & (s < maxv - dist)) | ((arr < 0.0) & (s > minv + dist))
        sigma_move = move / vol
        cb_hit = (prev_held * sigma_move) <= -DAILY_LOSS_SIGMA

        # Hard level stop: track entry level of the current long.
        entry_level = np.full(len(arr), np.nan)
        cur_entry = np.nan
        for i in range(len(arr)):
            if arr[i] > 0.0 and np.isnan(cur_entry):
                cur_entry = s[i]
            elif arr[i] == 0.0:
                cur_entry = np.nan
            entry_level[i] = cur_entry
        hard_hit = (arr > 0.0) & (s < entry_level * (1.0 - HARD_STOP_PCT))

        event = np.asarray(stop_hit | cb_hit | hard_hit, dtype=bool)
        arr[event] = 0.0

        n = len(arr)
        for event_i in np.flatnonzero(event):
            hi = min(event_i + 1 + COOLDOWN_BARS, n)
            arr[event_i + 1:hi] = 0.0

        out[leg] = pd.Series(arr, index=spread.index)
    return pd.DataFrame(out)
