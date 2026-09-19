import numpy as np
import pandas as pd

from weather_experiment import (
    CORE3,
    gate_state,
    hdd_z,
    load_weather,
    permute_weather_z,
    run_experiment,
)


def test_hdd_z_is_causal_and_clipped():
    dates = pd.date_range("2010-01-01", periods=500, freq="D")
    temperature = pd.Series(10.0 + np.sin(np.arange(len(dates)) / 8), index=dates)
    z = hdd_z(temperature, min_obs=2)
    assert z.index.equals(dates)
    assert z.abs().dropna().max() <= 8.0

    changed = temperature.copy()
    changed.iloc[-1] = -100.0
    changed_z = hdd_z(changed, min_obs=2)
    before_last = dates[:-1]
    assert np.allclose(z.loc[before_last], changed_z.loc[before_last], equal_nan=True)


def test_gate_state_applies_weather_one_day_later():
    z = pd.Series([0.0, -1.1, -1.1, -0.4, 0.0], index=pd.date_range("2024-01-01", periods=5))
    state = gate_state(z, threshold=-1.0, reenter=-0.5)
    assert state.iloc[0] == 1.0
    assert state.iloc[1] == 1.0
    assert state.iloc[2] == 0.0
    assert state.iloc[3] == 0.0
    assert state.iloc[4] == 1.0


def test_cached_weather_has_expected_series():
    weather = load_weather("NYC")
    assert len(weather) > 7000
    assert weather.index.is_monotonic_increasing
    assert weather.notna().all()


def test_permutation_is_seeded_and_preserves_index():
    z = pd.Series(np.arange(20, dtype=float), index=pd.date_range("2020-01-01", periods=20))
    one = permute_weather_z(z, seed=11)
    two = permute_weather_z(z, seed=11)
    assert one.equals(two)
    assert one.index.equals(z.index)
    assert sorted(one.tolist()) == sorted(z.tolist())


def test_run_reports_fixed_core3_and_controls():
    dates = pd.bdate_range("2020-01-01", periods=240)
    t = np.arange(len(dates))
    panel = pd.DataFrame(
        {
            "CL": 50 + np.sin(t / 11),
            "BZ": 52 + np.sin(t / 13),
            "RB": 2.2 + 0.1 * np.sin(t / 9),
            "HO": 2.1 + 0.1 * np.cos(t / 10),
            "NG": 3.0 + 0.2 * np.sin(t / 15),
        },
        index=dates,
    )
    weather = pd.Series(10 + np.sin(t / 7), index=dates)
    result = run_experiment(panel, weather_data={"NYC": weather, "HOUSTON": weather + 1}, permutations=2, overlay=False)
    assert result["control_inputs"]["core3"] == list(CORE3)
    assert result["negative_control"]["permutations"] == 2
    assert set(result["books"]) >= {"CORE3", "CORE3+NGW"}
