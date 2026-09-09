"""Crack Spread Hedging Pressure -> Mean Reversion, v2 (long-biased).

v1 finding (see harness baseline): the 20-day z-score fade has no edge on the
real crack spread. The mean-reversion edge lives at long lookbacks and is
asymmetric:
  - Buying a CRUSHED crack (z < -1.5 vs 120d mean) reverts +7% over 20d,
    robust across trend regimes.
  - Fading a STRETCHED crack (z > +1.5) has no reliable edge and loses in
    trending regimes (first half of the sample: shorting the stretch was
    run over +18.7% in 20d).
So v2 is long-biased: it buys the crack when crushed and does not short it.
The optional SHORT_STRETCHED flag re-enables a short only in a rangebound
regime, for comparison.

Bleedout note (from the data): a crushed crack bleeds ~0.5% over the first
5 days before reverting. The trailing stop is set wide enough to ride that
bleedout; the circuit breaker still catches instant-gap tails.

Lookahead note: all rolling statistics use data strictly before bar t
(inputs shifted one bar), so nothing at t sees bar t's close.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# --- signal parameters ---------------------------------------------------
Z_LOOKBACK = 120      # rolling window for the z-score mean and std
Z_ENTRY = 1.5         # enter long when the crack is crushed past this z
Z_EXIT = -0.5         # exit long when the z-score recovers to this level
MIN_OBS = 60          # min observations before a rolling stat is valid
Z_MIN_STD_REL = 1e-4  # std must be meaningful relative to |level| to trust z
Z_MAX_Z = 8.0         # clip z to bound the effect of tail bars

# --- optional short side (off by default: no edge in sample) -------------
SHORT_STRETCHED = False
SHORT_ENTRY = 1.5     # enter short when stretched past this z
SHORT_EXIT = 0.5      # exit short when z decays back inside this band
TREND_LOOKBACK = 60   # trend = 20d change in the 60d average crack
TREND_CHANGE = 20
TREND_RANGE = 1.0     # |trend| below this = rangebound (short only here)

# --- crack construction --------------------------------------------------
# RB and HO futures trade in USD per gallon; CL trades in USD per barrel.
# One barrel = 42 gallons, so the product leg must be converted to per-barrel
# before subtracting crude, or the level is a unit-mismatched meaningless
# number (e.g. ~ -70 when the real crack is ~ +20).
GALLONS_PER_BARREL = 42.0
CRACK_WEIGHTS = {"RB": 2.0 / 3.0, "HO": 1.0 / 3.0}  # 3:2:1 product weights
_SYMBOL_ALIASES = {
    "crude": "CL", "wti": "CL", "cl": "CL",
    "rb": "RB", "gasoline": "RB", "rbob": "RB",
    "ho": "HO", "heating": "HO", "ulsd": "HO", "diesel": "HO",
}

# --- sizing parameters ---------------------------------------------------
VOL_LOOKBACK = 20     # rolling window for realized volatility
VOL_TARGET = 0.20     # annualized volatility target
MAX_LEVERAGE = 1.0    # cap on |position| (fraction of capital)
VOL_FALLBACK = 0.50   # conservative scale when no vol history exists yet
SHORT_MIN_OBS = 10    # min observations for the short sizing/risk windows

# --- risk parameters -----------------------------------------------------
STOP_LOOKBACK = 10       # trailing-stop reference window (bars)
STOP_SIGMA = 1.25        # trailing-stop distance in multi-day volatility units
DAY_STD_LOOKBACK = 20    # window for the daily volatility of absolute moves
DAILY_LOSS_SIGMA = 3.0   # flatten when an adverse one-bar move exceeds this many daily volatilities
COOLDOWN_BARS = 5        # hold the book flat this many bars after a forced flatten


def _canonical_symbol(name: object) -> str:
    """Map a panel column label to a canonical symbol, or '' when unknown."""
    key = str(name).strip().lower()
    return _SYMBOL_ALIASES.get(key, "")


def _crack_spread(prices) -> "tuple[pd.Series, bool]":
    """Return the tradable crack level series and whether a panel was used.

    A single Series is passed through unchanged: it is assumed to already be
    the crack spread level. A DataFrame is searched for CL, RB, HO columns,
    case-insensitively and by common aliases. When CL exists, the spread is
    the weighted product average (converted to per-barrel) minus crude, per
    barrel. Missing products are dropped and the remaining weights are
    renormalized, so an RB-only panel yields spread = RB - CL. When no symbol
    column is found, the first column is used as a fallback, with a warning.
    """
    if isinstance(prices, pd.Series):
        return prices.astype(float), False

    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pd.Series or a pd.DataFrame")

    canonical: dict = {}
    for label in prices.columns:
        sym = _canonical_symbol(label)
        if sym:
            canonical.setdefault(sym, label)

    cl_col = canonical.get("CL")
    if cl_col is None:
        warnings.warn(
            "no CL column found in the price panel; falling back to the "
            "first column, which may not express the crack spread thesis",
            RuntimeWarning,
            stacklevel=2,
        )
        return prices.iloc[:, 0].astype(float), False

    products = []
    for sym in ("RB", "HO"):
        if sym in canonical:
            products.append((canonical[sym], CRACK_WEIGHTS[sym]))

    if not products:
        warnings.warn(
            "no RB or HO column found in the price panel; a raw CL series "
            "does not express the crack spread thesis",
            RuntimeWarning,
            stacklevel=2,
        )
        return prices[cl_col].astype(float), False

    total_weight = sum(weight for _, weight in products)
    product_level = sum(
        prices[col] * (weight / total_weight) for col, weight in products
    )
    # Convert the per-gallon product level to per-barrel before subtracting CL.
    spread = product_level * GALLONS_PER_BARREL - prices[cl_col]
    return spread.astype(float), True


def generate_signals(prices: pd.Series) -> pd.Series:
    """Return a signal series aligned to `prices.index`.

    Convention: +1 = long, -1 = short, 0 = flat. The series traded is the
    crack spread level (see _crack_spread). Long when the crack is crushed
    (z < -Z_ENTRY vs its 120d mean), exit when z recovers to Z_EXIT. The
    short side is optional and only fires in a rangebound regime.
    """
    spread, _ = _crack_spread(prices)

    # The z-score uses only closes strictly before bar t (shift(1)).
    prev = spread.shift(1)
    mean = prev.rolling(Z_LOOKBACK, min_periods=MIN_OBS).mean()
    std = prev.rolling(Z_LOOKBACK, min_periods=MIN_OBS).std()
    min_std = Z_MIN_STD_REL * mean.abs()
    valid = std.fillna(0.0) > min_std.fillna(0.0)
    z = (prev - mean) / std.where(valid)
    z = z.replace([np.inf, -np.inf], np.nan).clip(-Z_MAX_Z, Z_MAX_Z)

    # Trend (strictly before bar t): 20d change in the 60d average crack.
    trend = (
        prev.rolling(TREND_LOOKBACK, min_periods=MIN_OBS).mean().diff(TREND_CHANGE)
    )

    values = np.zeros(len(spread), dtype=float)
    state = 0.0
    z_arr = z.to_numpy(dtype=float)
    tr_arr = trend.to_numpy(dtype=float)
    for i in range(len(spread)):
        zz = z_arr[i]
        if np.isnan(zz):
            values[i] = 0.0
            continue
        if state == 0.0:
            if zz <= -Z_ENTRY:
                state = 1.0
            elif SHORT_STRETCHED and zz >= SHORT_ENTRY and abs(tr_arr[i]) < TREND_RANGE:
                state = -1.0
        elif state == 1.0:
            if zz >= Z_EXIT:
                state = 0.0
        else:  # state == -1.0
            if zz <= SHORT_EXIT:
                state = 0.0
        values[i] = state

    return pd.Series(values, index=prices.index)


def size_positions(signal: pd.Series, prices: pd.Series) -> pd.Series:
    """Turn a directional signal into a position size (fraction of capital).

    Vol targeting: scale the signal so the portfolio targets a fixed
    annualized volatility, capped at MAX_LEVERAGE. Returns are measured
    against a rolling typical |level| so the sizing stays finite when the
    crack spread is near zero or negative. When rolling volatility history
    is absent, the expanding (full-history) volatility is used, then a
    conservative VOL_FALLBACK, so a quiet warm-up never gets full size.
    """
    spread, _ = _crack_spread(prices)

    # Relative returns use a rolling typical |level| known before bar t.
    level = spread.abs().rolling(VOL_LOOKBACK, min_periods=SHORT_MIN_OBS).mean().shift(1)
    rel_ret = spread.diff() / level
    realized = rel_ret.rolling(VOL_LOOKBACK, min_periods=SHORT_MIN_OBS).std()
    realized = realized.shift(1).replace(0.0, np.nan) * np.sqrt(252)

    scale = (VOL_TARGET / realized).clip(upper=MAX_LEVERAGE)

    uncond = rel_ret.expanding(min_periods=SHORT_MIN_OBS).std().shift(1).replace(0.0, np.nan)
    uncond = uncond * np.sqrt(252)
    fallback = (VOL_TARGET / uncond).clip(upper=MAX_LEVERAGE)

    use = scale.fillna(fallback).fillna(VOL_FALLBACK)
    positions = (signal * use).clip(-MAX_LEVERAGE, MAX_LEVERAGE)
    return positions.fillna(0.0)


def apply_risk_rules(positions: pd.Series, prices: pd.Series) -> pd.Series:
    """Apply risk overlays and return the final position series.

    1. Exposure cap: |position| never exceeds MAX_LEVERAGE.
    2. Trailing stop: flatten longs that break below the recent rolling max
       by STOP_SIGMA multi-day volatilities, and shorts that break above the
       recent rolling min by the same distance. The distance is set in the
       crack level's own units, so it works when the level is near zero or
       negative. This cuts the bleedout losses called out in the risk notes.
    3. Daily-loss circuit breaker: flatten when the prior held position moves
       against it by more than DAILY_LOSS_SIGMA daily volatilities in one
       bar (instant-gap protection).
    4. Cooldown: after any forced flatten, hold the book flat for
       COOLDOWN_BARS so a fresh signal cannot re-enter into the same event.
    """
    spread, _ = _crack_spread(prices)
    out = positions.fillna(0.0).clip(-MAX_LEVERAGE, MAX_LEVERAGE)

    # Daily volatility of absolute moves, strictly before bar t.
    day_std = spread.diff().rolling(DAY_STD_LOOKBACK, min_periods=SHORT_MIN_OBS).std()
    vol = day_std.shift(1).replace(0.0, np.nan).to_numpy(dtype=float)

    s = spread.to_numpy(dtype=float)
    arr = out.to_numpy(dtype=float).copy()
    prev_held = out.shift(1).fillna(0.0).to_numpy(dtype=float)
    move = spread.diff().to_numpy(dtype=float)

    maxv = (
        spread.shift(1).rolling(STOP_LOOKBACK, min_periods=SHORT_MIN_OBS).max().to_numpy(dtype=float)
    )
    minv = (
        spread.shift(1).rolling(STOP_LOOKBACK, min_periods=SHORT_MIN_OBS).min().to_numpy(dtype=float)
    )
    dist = vol * STOP_SIGMA * np.sqrt(STOP_LOOKBACK)

    stop_hit = ((arr > 0.0) & (s < maxv - dist)) | ((arr < 0.0) & (s > minv + dist))
    sigma_move = move / vol
    cb_hit = (prev_held * sigma_move) <= -DAILY_LOSS_SIGMA

    event = np.asarray(stop_hit | cb_hit, dtype=bool)
    arr[event] = 0.0

    n = len(arr)
    for event_i in np.flatnonzero(event):
        hi = min(event_i + 1 + COOLDOWN_BARS, n)
        arr[event_i + 1:hi] = 0.0

    return pd.Series(arr, index=prices.index)
