"""Regression tests for the backtest return basis.

A derived spread level can cross zero. pct_change() divides by the level, so
near a crossing it explodes and books phantom P&L. These tests pin the fix:
ordinary price series are unchanged, cross-zero spreads stay finite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algoterminal.research.backtest import asset_returns_from_prices, run_backtest


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def test_ordinary_prices_use_pct_change_unchanged() -> None:
    prices = pd.Series(np.linspace(50.0, 90.0, 60), index=_idx(60))
    got = asset_returns_from_prices(prices)
    want = prices.pct_change().fillna(0.0)
    pd.testing.assert_series_equal(got, want)


def test_spread_crossing_zero_stays_finite() -> None:
    # BZ - CL style basis that crosses zero mid-series.
    prices = pd.Series(np.linspace(-2.0, 2.0, 60), index=_idx(60))
    got = asset_returns_from_prices(prices)
    assert np.isfinite(got.to_numpy()).all()
    # pct_change would blow up here; the spread basis must stay bounded.
    naive = prices.pct_change().fillna(0.0)
    assert naive.abs().max() > 1.0
    assert got.abs().max() < 1.0


def test_short_series_does_not_crash() -> None:
    prices = pd.Series([-1.0, 0.0, 1.0], index=_idx(3))
    got = asset_returns_from_prices(prices)
    assert np.isfinite(got.to_numpy()).all()


def test_run_backtest_uses_the_spread_basis() -> None:
    """End-to-end guard: the CALL SITE must not regress to pct_change.

    A unit test on the helper alone would still pass if run_backtest went
    back to pct_change, so this exercises the real entry point.
    """
    from types import SimpleNamespace

    # spread level that crosses zero, so pct_change would explode
    prices = pd.Series(np.linspace(-2.0, 2.0, 60), index=_idx(60))
    strat = SimpleNamespace(
        generate_signals=lambda p: pd.Series(1.0, index=p.index),
        size_positions=lambda sig, p: sig,
        apply_risk_rules=lambda sized, p: sized,
    )
    result = run_backtest(strat, prices)
    assert np.isfinite(result.returns.to_numpy()).all()
    # with pct_change the equity curve would be destroyed by phantom returns
    assert result.returns.abs().max() < 1.0
