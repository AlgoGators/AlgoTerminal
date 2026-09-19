"""Tests for the modeled CORE3 options tail-protection screen."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from options_hedge_screen import (
    DEFAULT_CONFIG,
    black76_put_price,
    run_options_screen,
)


def test_black76_put_has_intrinsic_limit_and_positive_time_value():
    assert black76_put_price(100.0, 90.0, 1.0, 0.0) == pytest.approx(0.0)
    price = black76_put_price(100.0, 100.0, 30 / 365, 0.40)
    assert price > 0.0
    assert math.isfinite(price)


def test_screen_is_explicitly_modeled_and_keeps_quotes_unavailable():
    observations = pd.DataFrame(
        {
            "core3_return": [-0.08, 0.05, -0.02, 0.01],
            "gap_return": [-0.20, 0.10, -0.03, 0.02],
            "gap_day": [True, False, True, False],
            "forward": [100.0] * 4,
            "realized_vol": [0.40] * 4,
        },
        index=pd.date_range("2024-01-02", periods=4, freq="B"),
    )

    result = run_options_screen(observations)

    assert result["metadata"]["historical_option_quotes"] == "unavailable"
    assert result["metadata"]["pricing"] == "modeled_black76_intrinsic_gap_proxy"
    assert result["metadata"]["fixed_delta"] == DEFAULT_CONFIG.long_put_delta
    assert result["metadata"]["fixed_expiry_days"] == DEFAULT_CONFIG.expiry_days
    assert result["metadata"]["fixed_iv_markup"] == DEFAULT_CONFIG.iv_markup
    assert result["base"]["daily"]["modeled_premium"].gt(0).all()
    assert "historical_option_quote" not in result["base"]["daily"]


def test_gap_comparison_and_doubled_cost_are_causal_and_directional():
    observations = pd.DataFrame(
        {
            "core3_return": [-0.08, 0.05, -0.02, 0.01],
            "gap_return": [-0.20, 0.10, -0.03, 0.02],
            "gap_day": [True, False, True, False],
            "forward": [100.0] * 4,
            "realized_vol": [0.40] * 4,
        },
        index=pd.date_range("2024-01-02", periods=4, freq="B"),
    )

    result = run_options_screen(observations)
    base = result["base"]["daily"]
    doubled = result["doubled_cost"]["daily"]

    assert list(result["gap_comparison"].index) == list(observations.index[[0, 2]])
    assert {
        "core3_return",
        "hedge_return",
        "combined_return",
    }.issubset(result["gap_comparison"].columns)
    assert (doubled["combined_return"] <= base["combined_return"]).all()
    assert base.loc[observations.index[0], "hedge_payoff"] > 0.0
    assert base.loc[observations.index[1], "hedge_payoff"] == 0.0
    assert result["base"]["summary"]["gap_loss_reduction"] >= 0.0
