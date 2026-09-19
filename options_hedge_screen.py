"""Minimal modeled tail-protection screen for the frozen CORE3 book.

This is a plausibility screen, not a historical options backtest.  Historical
option settlements and executable bid/ask quotes are unavailable, so every
premium below is a Black-76-style model value.  The gap payoff is an intrinsic
value proxy on the mapped underlying move.  It does not invent option quotes.

The screen keeps the requested construction fixed: a 30-delta long put, a
7.5-delta short put, 52 days to expiry, a 21-day roll cadence, and a 1.25x IV
markup over the supplied lagged realized volatility.  Its input observations
must already be causal t-1 observations from the frozen CORE3 test.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, isfinite, log, sqrt
from typing import Any

import pandas as pd

HISTORICAL_QUOTES_STATUS = "unavailable"


@dataclass(frozen=True)
class ScreenConfig:
    """Pre-registered assumptions for the modeled spread screen."""

    long_put_delta: float = 0.30
    short_put_delta: float = 0.075
    expiry_days: int = 52
    roll_days: int = 21
    iv_markup: float = 1.25
    protection_size: float = 1.0
    bid_ask_cost: float = 0.0010
    roll_cost: float = 0.0010
    annual_days: int = 252


DEFAULT_CONFIG = ScreenConfig()


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _normal_ppf(probability: float) -> float:
    """Inverse standard normal CDF using the Acklam rational approximation."""
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must be between zero and one")

    # Coefficients are from Peter J. Acklam's public-domain approximation.
    a = (
        -3.969683028665376e1,
        2.209460984245205e2,
        -2.759285104469687e2,
        1.383577518672690e2,
        -3.066479806614716e1,
        2.506628277459239,
    )
    b = (
        -5.447609879822406e1,
        1.615858368580409e2,
        -1.556989798598866e2,
        6.680131188771972e1,
        -1.328068155288572e1,
    )
    c = (
        -7.784894002430293e-3,
        -3.223964580411365e-1,
        -2.400758277161838e0,
        -2.549732539343734e0,
        4.374664141464968e0,
        2.938163982698783e0,
    )
    d = (
        7.784695709041462e-3,
        3.224671290700398e-1,
        2.445134137142996e0,
        3.754408661907416e0,
    )
    low = 0.02425
    high = 1.0 - low

    def horner(coefficients: tuple[float, ...], value: float) -> float:
        result = coefficients[0]
        for coefficient in coefficients[1:]:
            result = result * value + coefficient
        return result

    if probability < low:
        q = sqrt(-2.0 * log(probability))
        return horner(c, q) / (horner(d, q) * q + 1.0)
    if probability > high:
        q = sqrt(-2.0 * log(1.0 - probability))
        return -horner(c, q) / (horner(d, q) * q + 1.0)

    q = probability - 0.5
    r = q * q
    return horner(a, r) * q / (horner(b, r) * r + 1.0)


def black76_put_price(
    forward: float,
    strike: float,
    expiry_years: float,
    implied_volatility: float,
    discount_factor: float = 1.0,
) -> float:
    """Return a Black-76 European put price in forward price units.

    Rates are represented by the supplied discount factor.  A zero-volatility
    or zero-expiry input returns discounted intrinsic value.
    """
    values = (forward, strike, expiry_years, implied_volatility, discount_factor)
    if not all(isfinite(value) for value in values):
        raise ValueError("Black-76 inputs must be finite")
    if forward <= 0.0 or strike <= 0.0 or expiry_years < 0.0:
        raise ValueError("forward and strike must be positive; expiry cannot be negative")
    if implied_volatility < 0.0 or discount_factor <= 0.0:
        raise ValueError("volatility and discount factor must be non-negative")

    if expiry_years == 0.0 or implied_volatility == 0.0:
        return discount_factor * max(strike - forward, 0.0)

    volatility_time = implied_volatility * sqrt(expiry_years)
    d1 = (log(forward / strike) + 0.5 * volatility_time**2) / volatility_time
    d2 = d1 - volatility_time
    return discount_factor * (
        strike * _normal_cdf(-d2) - forward * _normal_cdf(-d1)
    )


def put_strike_for_delta(
    forward: float,
    put_delta: float,
    expiry_years: float,
    implied_volatility: float,
) -> float:
    """Return the strike whose Black-76 absolute put delta matches ``put_delta``."""
    if not 0.0 < put_delta < 1.0:
        raise ValueError("put_delta must be between zero and one")
    if forward <= 0.0 or expiry_years <= 0.0 or implied_volatility <= 0.0:
        raise ValueError("forward, expiry, and volatility must be positive")

    d1 = -_normal_ppf(put_delta)
    volatility_time = implied_volatility * sqrt(expiry_years)
    return forward * exp(-d1 * volatility_time + 0.5 * volatility_time**2)


def _validate_observations(observations: pd.DataFrame) -> pd.DataFrame:
    required = {"core3_return", "gap_return", "gap_day", "forward", "realized_vol"}
    missing = required.difference(observations.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if observations.empty:
        raise ValueError("observations must not be empty")

    frame = observations.copy()
    numeric = ["core3_return", "gap_return", "forward", "realized_vol"]
    if frame[numeric].isna().any().any() or frame["gap_day"].isna().any():
        raise ValueError("observations contain missing values")
    if (frame["forward"] <= 0.0).any() or (frame["realized_vol"] <= 0.0).any():
        raise ValueError("forward and realized_vol must be positive")
    if ((frame["gap_return"] <= -1.0) | (frame["gap_return"] > 10.0)).any():
        raise ValueError("gap_return must describe a finite price move")
    frame["gap_day"] = frame["gap_day"].astype(bool)
    return frame


def _validate_config(config: ScreenConfig) -> None:
    if not 0.0 < config.short_put_delta < config.long_put_delta < 1.0:
        raise ValueError("short delta must be below long delta and both in (0, 1)")
    if config.expiry_days <= 0 or config.roll_days <= 0:
        raise ValueError("expiry_days and roll_days must be positive")
    if config.iv_markup <= 0.0 or config.protection_size < 0.0:
        raise ValueError("iv_markup and protection_size must be positive")
    if config.bid_ask_cost < 0.0 or config.roll_cost < 0.0:
        raise ValueError("costs must be non-negative")


def _modeled_case(
    observations: pd.DataFrame, config: ScreenConfig, cost_multiplier: float
) -> dict[str, Any]:
    rows: list[dict[str, float]] = []
    expiry_years = config.expiry_days / config.annual_days
    daily_cost = (
        config.bid_ask_cost + config.roll_cost
    ) * cost_multiplier / config.roll_days

    for timestamp, row in observations.iterrows():
        forward = float(row["forward"])
        volatility = float(row["realized_vol"]) * config.iv_markup
        long_strike = put_strike_for_delta(
            forward, config.long_put_delta, expiry_years, volatility
        )
        short_strike = put_strike_for_delta(
            forward, config.short_put_delta, expiry_years, volatility
        )
        long_premium = black76_put_price(
            forward, long_strike, expiry_years, volatility
        ) / forward
        short_premium = black76_put_price(
            forward, short_strike, expiry_years, volatility
        ) / forward
        premium = max(long_premium - short_premium, 0.0)

        next_forward = forward * (1.0 + float(row["gap_return"]))
        long_intrinsic = max(long_strike - next_forward, 0.0) / forward
        short_intrinsic = max(short_strike - next_forward, 0.0) / forward
        payoff = (
            config.protection_size
            * max(long_intrinsic - short_intrinsic, 0.0)
            if bool(row["gap_day"])
            else 0.0
        )
        carry_cost = premium / config.roll_days
        hedge_return = payoff - carry_cost - daily_cost
        rows.append(
            {
                "date": timestamp,
                "modeled_premium": premium,
                "long_strike": long_strike,
                "short_strike": short_strike,
                "hedge_payoff": payoff,
                "carry_cost": carry_cost,
                "transaction_cost": daily_cost,
                "hedge_return": hedge_return,
                "core3_return": float(row["core3_return"]),
                "combined_return": float(row["core3_return"]) + hedge_return,
                "gap_day": bool(row["gap_day"]),
            }
        )

    daily = pd.DataFrame(rows).set_index("date")
    gap = daily[daily["gap_day"]]
    worst_core3 = float(gap["core3_return"].min())
    worst_combined = float(gap["combined_return"].min())
    reduction = (
        (worst_combined - worst_core3) / abs(worst_core3)
        if worst_core3 < 0.0
        else float("nan")
    )
    summary = {
        "annualized_carry": float(
            daily["modeled_premium"].mean()
            * config.annual_days
            / config.roll_days
        ),
        "annualized_transaction_cost": float(
            daily["transaction_cost"].mean() * config.annual_days
        ),
        "worst_gap_core3": worst_core3,
        "worst_gap_combined": worst_combined,
        "gap_loss_reduction": reduction,
        "mean_combined_return": float(daily["combined_return"].mean()),
    }
    return {"daily": daily, "summary": summary}


def run_options_screen(
    observations: pd.DataFrame, config: ScreenConfig = DEFAULT_CONFIG
) -> dict[str, Any]:
    """Run base and doubled-cost modeled cases and compare marked gap days.

    ``realized_vol`` and all returns must be lagged inputs.  No option quote,
    fill, settlement, or historical bid/ask is accepted or fabricated here.
    """
    _validate_config(config)
    frame = _validate_observations(observations)
    base = _modeled_case(frame, config, cost_multiplier=1.0)
    doubled = _modeled_case(frame, config, cost_multiplier=2.0)
    gap_comparison = base["daily"].loc[base["daily"]["gap_day"], [
        "core3_return",
        "hedge_return",
        "combined_return",
    ]]
    metadata = {
        "strategy": "frozen CORE3",
        "historical_option_quotes": HISTORICAL_QUOTES_STATUS,
        "historical_option_quotes_available": False,
        "pricing": "modeled_black76_intrinsic_gap_proxy",
        "fixed_delta": config.long_put_delta,
        "fixed_short_delta": config.short_put_delta,
        "fixed_expiry_days": config.expiry_days,
        "fixed_roll_days": config.roll_days,
        "fixed_iv_markup": config.iv_markup,
        "carry": "modeled premium amortized over roll_days",
        "cost_sensitivity": "base and doubled bid-ask plus roll cost",
    }
    return {
        "base": base,
        "doubled_cost": doubled,
        "gap_comparison": gap_comparison,
        "metadata": metadata,
    }


# Short alias for callers that treat this module as a screen rather than a run.
screen_options = run_options_screen


if __name__ == "__main__":
    print("Historical option quotes: unavailable")
    print("Use run_options_screen() with causal CORE3 observations.")
