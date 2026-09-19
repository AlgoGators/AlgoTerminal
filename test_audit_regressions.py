"""Regression checks for the frozen audit-remediation patch."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


book = load_module("audit_book", "book_oos_v4.py")
engine = load_module("audit_engine", "engine_v2.py")


def test_book_hard_stop_caps_long_and_short_adverse_moves():
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    long_level = pd.Series([100.0, 100.0, 79.0], index=index)
    short_level = pd.Series([100.0, 100.0, 121.0], index=index)
    positions = pd.Series(1.0, index=index)
    short_positions = pd.Series(-1.0, index=index)

    assert book.leg_risk(positions, long_level, trailing_stop=False).iloc[-1] == 0.0
    assert book.leg_risk(short_positions, short_level, trailing_stop=False).iloc[-1] == 0.0
    assert book.leg_risk(positions, pd.Series([100.0, 100.0, 101.0], index=index), trailing_stop=False).iloc[-1] == 1.0
    assert book.leg_risk(short_positions, pd.Series([100.0, 100.0, 99.0], index=index), trailing_stop=False).iloc[-1] == -1.0


def test_engine_hard_stop_caps_long_and_short_adverse_moves():
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    long_level = pd.Series([100.0, 100.0, 79.0], index=index)
    short_level = pd.Series([100.0, 100.0, 121.0], index=index)

    assert engine.leg_risk(pd.Series(1.0, index=index), long_level, False).iloc[-1] == 0.0
    assert engine.leg_risk(pd.Series(-1.0, index=index), short_level, False).iloc[-1] == 0.0
    assert engine.leg_risk(pd.Series(1.0, index=index), pd.Series([100.0, 100.0, 101.0], index=index), False).iloc[-1] == 1.0
    assert engine.leg_risk(pd.Series(-1.0, index=index), pd.Series([100.0, 100.0, 99.0], index=index), False).iloc[-1] == -1.0


def test_proxy_roll_selects_primary_stream():
    stub = pd.DataFrame({"factor": [1.0]})
    proxy = pd.DataFrame({"factor": [2.0]})
    assert engine.select_primary_stream(stub, proxy, use_proxy=False) is stub
    assert engine.select_primary_stream(stub, proxy, use_proxy=True) is proxy


def test_high_volatility_threshold_is_prefix_causal():
    index = pd.date_range("2020-01-01", periods=80, freq="D")
    front = pd.Series(100.0, index=index)
    front.iloc[20:40] = np.linspace(100.0, 110.0, 20)
    front.iloc[40:60] = np.linspace(110.0, 108.0, 20)
    front.iloc[60:] = np.linspace(108.0, 108.5, 20)
    prefix = engine.causal_high_vol_mask(front.iloc[:60])
    extended = engine.causal_high_vol_mask(front)
    pd.testing.assert_series_equal(prefix, extended.iloc[:60], check_names=False)


def test_book_panel_falls_back_to_durable_panel(tmp_path):
    temporary = tmp_path / "temporary.parquet"
    durable = tmp_path / "panel_v2.parquet"
    durable.touch()
    assert book.resolve_panel_path(temporary, durable) == durable
