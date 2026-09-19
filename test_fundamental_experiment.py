import numpy as np
import pandas as pd

from fundamental_experiment import (
    CORE3,
    build_fundamental_features,
    daily_feature_state,
    fundamental_scale,
    permute_release_features,
    run_experiment,
)


def _weekly_series(values):
    dates = pd.date_range("2018-01-05", periods=len(values), freq="7D")
    return pd.Series(values, index=dates, dtype=float)


def test_features_use_prior_same_month_observations_and_release_lag():
    # min_obs=2 makes the causal boundary small enough for a unit fixture.
    gas = _weekly_series([100, 101, 103, 106, 110, 115])
    dist = _weekly_series([200, 201, 203, 206, 211, 217])
    util = _weekly_series([90, 89, 91, 88, 92, 87])
    features = build_fundamental_features(
        gas, dist, util, min_obs=2, lag_days=6
    )

    observation_dates = features["observation_date"].dropna()
    first = observation_dates.iloc[0]
    assert features.index[0] == first + pd.Timedelta(days=6)
    assert features.loc[features.index[0], "observation_date"] < features.index[0]

    # Changing a later release cannot change an earlier released feature.
    changed = build_fundamental_features(
        gas * pd.Series([1, 1, 1, 1, 1, 100], index=gas.index),
        dist,
        util,
        min_obs=2,
        lag_days=6,
    )
    common = features.index.intersection(changed.index)
    assert np.allclose(
        features.loc[common[:-1], "physical_score"],
        changed.loc[common[:-1], "physical_score"],
        equal_nan=True,
    )


def test_feature_formulas_include_utilization_and_product_stock_draws():
    dates = pd.date_range("2010-01-01", periods=20, freq="7D")
    gas = pd.Series(np.arange(100, 120), index=dates, dtype=float)
    dist = pd.Series(np.arange(200, 220), index=dates, dtype=float)
    util = pd.Series(np.arange(80, 100), index=dates, dtype=float)
    features = build_fundamental_features(gas, dist, util, min_obs=2)

    assert {"util_change_z", "gas_draw_z", "dist_draw_z", "product_draw_z", "physical_score"} <= set(features)
    assert np.allclose(
        features["physical_score"].dropna(),
        (features["product_draw_z"] - features["util_change_z"]).dropna(),
    )


def test_daily_state_starts_at_release_and_scale_uses_previous_close():
    release = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-05", "2024-01-12"]),
            "physical_score": [2.0, -2.0],
            "product_draw_z": [1.0, -1.0],
            "util_change_z": [-1.0, 1.0],
        },
        index=pd.to_datetime(["2024-01-11", "2024-01-18"]),
    )
    index = pd.date_range("2024-01-10", "2024-01-22", freq="B")
    daily = daily_feature_state(release, index)
    scale = fundamental_scale(daily)

    assert pd.isna(daily.loc["2024-01-10", "physical_score"])
    assert daily.loc["2024-01-11", "physical_score"] == 2.0
    assert scale.loc["2024-01-11"] == 1.0
    assert scale.shift(1).loc["2024-01-12"] == 1.0
    assert scale.shift(1).loc["2024-01-19"] == 0.0


def test_run_reports_frozen_baseline_scaled_and_negative_control():
    rng = np.random.default_rng(7)
    market_index = pd.bdate_range("2020-01-01", periods=240)
    t = np.arange(len(market_index))
    panel = pd.DataFrame(
        {
            "CL": 50 + np.sin(t / 11),
            "BZ": 52 + np.sin(t / 13),
            "RB": 2.2 + 0.1 * np.sin(t / 9),
            "HO": 2.1 + 0.1 * np.cos(t / 10),
            "NG": 3.0 + 0.2 * np.sin(t / 15),
        },
        index=market_index,
    )
    weekly_index = pd.date_range("1990-01-05", periods=1900, freq="7D")
    base = rng.normal(0, 1, len(weekly_index)).cumsum()
    fundamentals = {
        "gasoline": pd.Series(1000 + base, index=weekly_index),
        "distillate": pd.Series(700 + rng.normal(0, 1, len(base)).cumsum(), index=weekly_index),
        "utilization": pd.Series(80 + rng.normal(0, 0.2, len(base)).cumsum(), index=weekly_index),
    }
    result = run_experiment(panel, fundamentals, permutations=2, overlay=False)

    assert set(("baseline", "scaled", "factor_results", "negative_control")) <= set(result)
    assert set(result["factor_results"]["baseline"]) == set(CORE3)
    assert result["negative_control_returns"].shape[1] == 2
    assert set(result["scale"].dropna().unique()) <= {0.0, 0.5, 1.0}
    assert result["control_inputs"]["core3"] == list(CORE3)


def test_negative_control_permutation_is_seeded_and_preserves_release_dates():
    release = pd.DataFrame(
        {
            "observation_date": pd.date_range("2020-01-03", periods=4, freq="7D"),
            "physical_score": [0.1, 0.2, 0.3, 0.4],
            "product_draw_z": [0.5, 0.6, 0.7, 0.8],
            "util_change_z": [-0.1, -0.2, -0.3, -0.4],
        },
        index=pd.date_range("2020-01-09", periods=4, freq="7D"),
    )
    one = permute_release_features(release, seed=23)
    two = permute_release_features(release, seed=23)
    assert one.equals(two)
    assert one.index.equals(release.index)
    assert one["observation_date"].equals(release["observation_date"])
    assert sorted(one["physical_score"]) == sorted(release["physical_score"])
    assert set(CORE3) == {"crack_321", "cross_sectional", "bzwti"}
