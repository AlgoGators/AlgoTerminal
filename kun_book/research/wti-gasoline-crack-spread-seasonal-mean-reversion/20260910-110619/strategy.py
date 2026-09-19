"""Strategy for: WTI Crack Spread Seasonal Mean Reversion

Thesis:
    When the WTI 3:2:1 crack spread (refining margin) is seasonally crushed
    below its normal level for the time of year, refiners cut runs and shift
    yields, forcing the margin to revert toward its seasonal mean.

Target universe: crack-spreads (CRACK321, CRACKGAS, CRACKHO, BZWTI)
Primary instrument: CRACK321 -- the WTI 3:2:1 crack spread level, a derived
series (see algoterminal.data.derived_provider), not a raw market price.

This is factor F1 (the crack_321 leg) ported 1:1 from the standalone
`factor_book.py` 5-leg book -- see that file (backed up alongside this
record) for the full multi-factor version, which also trades crack_ho,
a cross-sectional crack ranking, natgas, and the Brent-WTI basis. Those
don't fit AlgoTerminal's single-instrument backtest engine and are not
ported here; this file is the honest single-factor subset.

The Backtest stage calls generate_signals -> size_positions -> apply_risk_rules.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --- parameters (same as factor_book.py's F1/crack_321 leg) ---------------
SMR_Z_LOOKBACK = 90
SMR_ENTRY = 0.75
SMR_EXIT = -0.5
SMR_MIN_OBS = 45
SEASON_MIN_OBS = 10
VOL_LOOKBACK = 20
VOL_TARGET = 0.50
MAX_LEV = 1.0
STOP_LOOKBACK = 10
STOP_SIGMA = 1.25
DAY_STD_LOOKBACK = 20
DAILY_LOSS_SIGMA = 3.0
COOLDOWN_BARS = 5
HARD_STOP_SIGMA = 3.0
ANCHOR_TREND_LOOKBACK = 252  # ~1 trading year
ANCHOR_TREND_MIN_OBS = 60
ANCHOR_TREND_Z_MIN = -0.5  # sigma: min self-scaled YoY drift of the seasonal anchor to allow a NEW entry


def _seasonal_mean(s: pd.Series, minobs: int = SEASON_MIN_OBS) -> pd.Series:
    out = pd.Series(np.nan, index=s.index)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        for i in range(len(idx)):
            t = idx[i]
            past = s.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m]
            if len(past) >= minobs:
                out.loc[t] = past.mean()
    return out


def _seasonal_z_and_anchor_trend(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    prev = s.shift(1)
    seas = _seasonal_mean(prev)
    adj = prev - seas
    mean = adj.rolling(SMR_Z_LOOKBACK, min_periods=SMR_MIN_OBS).mean()
    std = adj.rolling(SMR_Z_LOOKBACK, min_periods=SMR_MIN_OBS).std()
    min_std = 1e-4 * mean.abs()
    valid = std.fillna(0.0) > min_std.fillna(0.0)
    z = (adj - mean) / std.where(valid)
    z = z.replace([np.inf, -np.inf], np.nan).clip(-8.0, 8.0)

    # YoY drift of the seasonal anchor itself, not of the spread. The
    # reversion thesis ("crushed vs. the seasonal norm -> refiners cut runs
    # -> reverts to that norm") only holds if the norm is stable. When the
    # anchor itself has been sliding for a year (e.g. new refining capacity
    # structurally compressing margins), a fresh "crush" reading isn't a
    # mean-reversion setup -- it's the norm catching down to a new regime,
    # and buying it just catches a falling knife. Empirically (5y in-sample,
    # WTI 3:2:1): trades entered with the anchor flat-to-rising YoY netted
    # +125% combined; trades entered with the anchor down >2 std (in
    # CRACK321's own units, ~$2/bbl there) netted -30% at a 25% win rate --
    # 8 of the 10 straight losers behind this strategy's worst drawdown.
    #
    # Self-scaled (z-scored against its own expanding history), not a flat
    # dollar cutoff: CRACK321/CRACKGAS/CRACKHO trade at different price
    # scales and have different trend volatility (CRACKHO's trend std is
    # ~1.9x CRACK321's, CRACKGAS's ~0.7x, on this 5y sample) -- a single
    # dollar threshold copied across legs would be far too lenient on one
    # and too strict on another. In-sample-derived threshold; unconfirmed OOS.
    trend = seas - seas.shift(ANCHOR_TREND_LOOKBACK)
    trend_mean = trend.expanding(min_periods=ANCHOR_TREND_MIN_OBS).mean()
    trend_std = trend.expanding(min_periods=ANCHOR_TREND_MIN_OBS).std()
    trend_z = (trend - trend_mean) / trend_std.replace(0.0, np.nan)
    return z, trend_z


def _vol_scale(s: pd.Series, vt: float) -> pd.Series:
    level = s.abs().rolling(VOL_LOOKBACK, min_periods=10).mean().shift(1)
    rel = s.diff() / level
    rv = rel.rolling(VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan) * np.sqrt(252)
    scale = (vt / rv).clip(upper=MAX_LEV)
    uncond = rel.expanding(min_periods=10).std().shift(1).replace(0.0, np.nan) * np.sqrt(252)
    fallback = (vt / uncond).clip(upper=MAX_LEV)
    return scale.fillna(fallback).fillna(0.5).clip(upper=MAX_LEV)


def generate_signals(prices: pd.Series) -> pd.Series:
    """Seasonal mean-reversion state machine on the crack-321 level.

    Long when the deseasonalized z-score drops to/below -SMR_ENTRY, flat
    once it recovers to/above SMR_EXIT. New entries additionally require the
    seasonal anchor itself to not be sliding (see _seasonal_z_and_anchor_trend)
    -- this only gates fresh entries, not exits, so an existing hold still
    exits normally on its own -0.5 signal.
    """
    z, trend_z = _seasonal_z_and_anchor_trend(prices)
    zz = z.to_numpy(dtype=float)
    tz = trend_z.to_numpy(dtype=float)
    vals = np.zeros(len(prices))
    state = 0.0
    for i in range(len(prices)):
        if np.isnan(zz[i]):
            # No new information (std-validity guard tripped, or not enough
            # obs yet) -- hold the current state rather than forcing flat.
            # Forcing 0.0 here used to fire spurious exits mid-hold whenever
            # the seasonal std collapsed, with no real -0.5 exit signal
            # behind them.
            vals[i] = state
            continue
        # NaN trend_z (not enough history yet for the anchor's own trend
        # distribution) can't be judged as declining or not -- default to
        # allowing entry rather than silently suppressing early trading.
        entry_ok = np.isnan(tz[i]) or tz[i] >= ANCHOR_TREND_Z_MIN
        if state == 0.0 and zz[i] <= -SMR_ENTRY and entry_ok:
            state = 1.0
        elif state == 1.0 and zz[i] >= SMR_EXIT:
            state = 0.0
        vals[i] = state
    return pd.Series(vals, index=prices.index)


def size_positions(signal: pd.Series, prices: pd.Series) -> pd.Series:
    """Vol-target the signal to VOL_TARGET annualized vol, capped at MAX_LEV."""
    return signal * _vol_scale(prices, VOL_TARGET)


def apply_risk_rules(positions: pd.Series, prices: pd.Series) -> pd.Series:
    """Circuit breaker + hard level stop + trailing stop + cooldown.

    Trailing stop is on for this leg (matches factor_book.py's
    TRAILING_STOP_ON["crack_321"] = True): it caps the deep 2024-09
    drawdown on the crack legs specifically.
    """
    out = positions.fillna(0.0).clip(-MAX_LEV, MAX_LEV)
    s = prices.to_numpy(dtype=float)
    arr = out.to_numpy(dtype=float).copy()
    prev_held = out.shift(1).fillna(0.0).to_numpy(dtype=float)
    move = prices.diff().to_numpy(dtype=float)
    day_std = prices.diff().rolling(DAY_STD_LOOKBACK, min_periods=10).std()
    vol = day_std.shift(1).replace(0.0, np.nan).to_numpy(dtype=float)

    maxv = prices.shift(1).rolling(STOP_LOOKBACK, min_periods=10).max().to_numpy(dtype=float)
    minv = prices.shift(1).rolling(STOP_LOOKBACK, min_periods=10).min().to_numpy(dtype=float)
    dist = vol * STOP_SIGMA * np.sqrt(STOP_LOOKBACK)
    stop_hit = ((arr > 0.0) & (s < maxv - dist)) | ((arr < 0.0) & (s > minv + dist))

    sigma_move = move / vol
    cb_hit = (prev_held * sigma_move) <= -DAILY_LOSS_SIGMA

    entry_level = np.full(len(arr), np.nan)
    cur_entry = np.nan
    for i in range(len(arr)):
        if arr[i] > 0.0 and np.isnan(cur_entry):
            cur_entry = s[i]
        elif arr[i] == 0.0:
            cur_entry = np.nan
        entry_level[i] = cur_entry
    # Dollar/sigma distance from entry, not a percentage: the crack level
    # isn't a price, it can sit near zero or go negative in other regimes,
    # so a pct-of-entry stop is inconsistent in width (near-zero entries
    # give an absurdly tight stop, large entries an absurdly loose one).
    # This mirrors the trailing stop's own vol-distance construction, just
    # wider (HARD_STOP_SIGMA > STOP_SIGMA) since it's the catastrophic floor.
    hard_dist = vol * HARD_STOP_SIGMA * np.sqrt(STOP_LOOKBACK)
    hard_hit = (arr > 0.0) & (s < entry_level - hard_dist)

    event = np.asarray(stop_hit | cb_hit | hard_hit, dtype=bool)

    # A stop firing used to just pause the position for COOLDOWN_BARS and
    # then silently resume it, because generate_signals' internal `state`
    # never reset to 0 -- it only re-evaluates the *exit* (z >= -0.5) while
    # held, not the entry condition. Whether that auto-resume is desirable
    # turns out to depend entirely on regime: during 2022's volatile-but-
    # genuinely-mean-reverting energy-crisis unwind, several of the best
    # trades in this book were exactly this pattern (stopped out once on
    # the way, resumed, caught the rest of the reversion) -- blocking all
    # resumption unconditionally would cut those winners short too. During
    # 2024-25's persistent grind (declining anchor, see ANCHOR_TREND_MIN),
    # the same auto-resume just re-bought the same losing trade over and
    # over. So: gate resumption on the same anchor-trend regime check used
    # for fresh entries, not a blanket ban -- only refuse to resume while
    # the seasonal norm itself still looks like it's sliding.
    _, trend_z = _seasonal_z_and_anchor_trend(prices)
    tz = trend_z.to_numpy(dtype=float)
    raw_held = arr != 0.0
    blocked = False
    for i in range(len(arr)):
        if not raw_held[i]:
            blocked = False
            continue
        if event[i]:
            arr[i] = 0.0
            blocked = True
            continue
        if blocked:
            if np.isnan(tz[i]) or tz[i] >= ANCHOR_TREND_Z_MIN:
                blocked = False
            else:
                arr[i] = 0.0

    n = len(arr)
    for event_i in np.flatnonzero(event):
        hi = min(event_i + 1 + COOLDOWN_BARS, n)
        arr[event_i + 1 : hi] = 0.0
    return pd.Series(arr, index=prices.index)
