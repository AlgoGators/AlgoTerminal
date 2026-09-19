"""Causal refinery-margin experiment on the frozen CORE3 price book.

The EIA inputs are weekly observations.
A value dated at the week end is available six calendar days later.
No strategy parameter is fitted in this module.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

CORE3 = ("crack_321", "cross_sectional", "bzwti")
CRACK_FACTORS = ("crack_321", "cross_sectional")
RELEASE_LAG_DAYS = 6
MIN_SAME_MONTH_OBS = 12
SCORE_CUTOFF = 1.0
PRODUCT_CUTOFF = 0.5
TRADE_BPS = 5.0
ROLL_BPS = 20.0
WARMUP = 90


def _as_series(value, name: str) -> pd.Series:
    """Read a close-like input and return a clean, date-indexed series."""
    if isinstance(value, (str, Path)):
        frame = pd.read_csv(value, index_col=0, parse_dates=True)
        value = frame["close"] if "close" in frame else frame.iloc[:, 0]
    elif isinstance(value, pd.DataFrame):
        value = value["close"] if "close" in value else value.iloc[:, 0]
    if not isinstance(value, pd.Series):
        value = pd.Series(value, name=name)
    out = pd.to_numeric(value, errors="coerce").dropna().copy()
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out[~out.index.duplicated(keep="last")].sort_index().rename(name)


def same_month_expanding_z(series: pd.Series, min_obs: int = MIN_SAME_MONTH_OBS) -> pd.Series:
    """Z-score each value against earlier observations in the same month.

    The current observation is excluded from its reference sample.
    """
    s = _as_series(series, "value")
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for month in range(1, 13):
        dates = s.index[s.index.month == month]
        for date in dates:
            past = s[(s.index < date) & (s.index.month == month)]
            if len(past) < min_obs:
                continue
            sd = past.std(ddof=1)
            if pd.notna(sd) and sd > 1e-12:
                out.loc[date] = (s.loc[date] - past.mean()) / sd
    return out.clip(-8.0, 8.0)


def _lag_feature(z: pd.Series, lag_days: int) -> pd.Series:
    out = z.copy()
    out.index = out.index + pd.Timedelta(days=lag_days)
    out.index.name = "availability_date"
    return out[~out.index.duplicated(keep="last")].sort_index()


def build_fundamental_features(
    gasoline: pd.Series | pd.DataFrame | str | Path,
    distillate: pd.Series | pd.DataFrame | str | Path,
    utilization: pd.Series | pd.DataFrame | str | Path,
    *,
    min_obs: int = MIN_SAME_MONTH_OBS,
    lag_days: int = RELEASE_LAG_DAYS,
) -> pd.DataFrame:
    """Build lagged weekly utilization and product-flow features.

    The returned index is the first date on which each release is usable.
    ``observation_date`` retains the raw EIA period date.
    """
    gas = _as_series(gasoline, "gasoline_stocks")
    dist = _as_series(distillate, "distillate_stocks")
    util = _as_series(utilization, "utilization")
    raw = pd.concat([gas, dist, util], axis=1).dropna()
    if raw.empty:
        return pd.DataFrame(
            columns=[
                "observation_date", "gasoline_stocks", "distillate_stocks",
                "utilization", "gas_change", "distillate_change", "util_change",
                "util_change_z", "gas_draw_z", "dist_draw_z", "product_draw_z",
                "physical_score",
            ],
            index=pd.DatetimeIndex([], name="availability_date"),
        )

    gas_change = raw["gasoline_stocks"].diff()
    dist_change = raw["distillate_stocks"].diff()
    util_change = raw["utilization"].diff()
    product_change = raw["gasoline_stocks"].add(raw["distillate_stocks"]).diff()
    features = pd.DataFrame(
        {
            "observation_date": raw.index,
            "gasoline_stocks": raw["gasoline_stocks"].to_numpy(),
            "distillate_stocks": raw["distillate_stocks"].to_numpy(),
            "utilization": raw["utilization"].to_numpy(),
            "gas_change": gas_change.to_numpy(),
            "distillate_change": dist_change.to_numpy(),
            "util_change": util_change.to_numpy(),
            "util_change_z": same_month_expanding_z(util_change, min_obs).reindex(raw.index).to_numpy(),
            "gas_draw_z": -same_month_expanding_z(gas_change, min_obs).reindex(raw.index).to_numpy(),
            "dist_draw_z": -same_month_expanding_z(dist_change, min_obs).reindex(raw.index).to_numpy(),
            "product_draw_z": -same_month_expanding_z(product_change, min_obs).reindex(raw.index).to_numpy(),
        },
        index=raw.index,
    )
    features["physical_score"] = features["product_draw_z"] - features["util_change_z"]
    # A score is usable only when both the product and utilization inputs exist.
    features = features.dropna(subset=["physical_score", "product_draw_z"])
    features.index = features.index + pd.Timedelta(days=lag_days)
    features.index.name = "availability_date"
    return features[~features.index.duplicated(keep="last")].sort_index()


# Short alias for callers that use the report's terminology.
build_features = build_fundamental_features


def daily_feature_state(release_features: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Forward-fill releases onto a daily market index without backfilling."""
    daily_index = pd.DatetimeIndex(pd.to_datetime(index))
    if getattr(daily_index, "tz", None) is not None:
        daily_index = daily_index.tz_localize(None)
    releases = release_features.copy()
    releases.index = pd.DatetimeIndex(pd.to_datetime(releases.index))
    if getattr(releases.index, "tz", None) is not None:
        releases.index = releases.index.tz_localize(None)
    releases = releases[~releases.index.duplicated(keep="last")].sort_index()
    expanded = releases.reindex(releases.index.union(daily_index)).sort_index().ffill()
    return expanded.reindex(daily_index)


def fundamental_scale(daily_features: pd.DataFrame) -> pd.Series:
    """Return the pre-registered 0, 0.5, 1 exposure scale.

    Before the first physical release, the frozen baseline remains active.
    """
    score = daily_features.get("physical_score", pd.Series(np.nan, index=daily_features.index))
    product = daily_features.get("product_draw_z", pd.Series(np.nan, index=daily_features.index))
    full = score.ge(SCORE_CUTOFF) & product.ge(PRODUCT_CUTOFF)
    half = score.ge(0.0) & product.ge(0.0)
    scale = pd.Series(np.select([full, half], [1.0, 0.5], default=0.0), index=daily_features.index)
    return scale.where(score.notna() & product.notna(), 1.0).rename("fundamental_scale")


def permute_release_features(release_features: pd.DataFrame, seed: int = 23) -> pd.DataFrame:
    """Shuffle released values while retaining the historical release dates."""
    out = release_features.copy()
    numeric = out.select_dtypes(include=[np.number]).columns
    if len(out) and len(numeric):
        permutation = np.random.default_rng(seed).permutation(len(out))
        out.loc[:, numeric] = out.iloc[permutation][numeric].to_numpy()
    return out


def _apply_costs(position: pd.Series, gross: pd.Series, *, trade_bps: float, roll_bps: float) -> pd.Series:
    turnover = position.diff().abs().fillna(0.0)
    return (
        gross.fillna(0.0)
        - trade_bps / 10000.0 * turnover
        - roll_bps / 252.0 / 10000.0 * position.abs()
    ).fillna(0.0)


def _apply_v2_overlay(book: pd.Series) -> pd.Series:
    """Use the existing v2 drawdown and volatility overlay without refitting."""
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (0.10 / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0).shift(1).fillna(1.0)
    scale = np.empty(len(book))
    state, equity, high_water = 1.0, 1.0, 1.0
    engine_equity, engine_high_water = 1.0, 1.0
    for i, value in enumerate(book.to_numpy(dtype=float)):
        scale[i] = state
        equity *= 1.0 + value * gear.iloc[i] * state
        high_water = max(high_water, equity)
        experienced_dd = equity / high_water - 1.0
        engine_equity *= 1.0 + value
        was_high = engine_high_water
        engine_high_water = max(engine_high_water, engine_equity)
        if engine_equity >= was_high:
            state = 1.0
        elif experienced_dd <= -0.10:
            state = 0.0
        elif experienced_dd <= -0.06:
            state = 0.5
    return book * pd.Series(scale, index=book.index) * gear


def _book_from_parts(positions: Mapping[str, pd.Series], returns: Mapping[str, pd.Series],
                    *, scale: pd.Series | None, index: pd.Index,
                    trade_bps: float, roll_bps: float, overlay: bool) -> tuple[pd.Series, pd.Series]:
    weights = {name: 1.0 / len(CORE3) for name in CORE3}
    books = []
    scaled_positions = {}
    for name in CORE3:
        pos = positions[name].reindex(index).fillna(0.0)
        gross = returns[name].reindex(index).fillna(0.0)
        if scale is not None and name in CRACK_FACTORS:
            pos = pos * scale
            gross = gross * scale.shift(1).fillna(1.0)
        scaled_positions[name] = pos
        books.append(_apply_costs(pos, gross, trade_bps=trade_bps, roll_bps=roll_bps) * weights[name])
    book = pd.concat(books, axis=1).sum(axis=1).rename("book")
    if overlay:
        book = _apply_v2_overlay(book)
    return book, pd.DataFrame(scaled_positions)


def _stats(returns: pd.Series, positions: pd.DataFrame | None = None) -> dict[str, float | int]:
    r = returns.dropna()
    if len(r) == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "vol": np.nan,
                "worst_day": np.nan, "trade_count": 0, "exposure_days": 0}
    equity = (1.0 + r).cumprod()
    years = len(r) / 252.0
    std = r.std()
    result = {
        "cagr": float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years else np.nan,
        "sharpe": float(r.mean() / std * np.sqrt(252)) if std else 0.0,
        "maxdd": float((equity / equity.cummax() - 1.0).min()),
        "vol": float(std * np.sqrt(252)) if std else 0.0,
        "worst_day": float(r.min()),
        "trade_count": 0,
        "exposure_days": 0,
    }
    if positions is not None:
        exposure = positions.abs().sum(axis=1).gt(0)
        result["exposure_days"] = int(exposure.sum())
        result["trade_count"] = int((exposure & ~exposure.shift(1, fill_value=False)).sum())
    return result


def _extract_inputs(fundamentals, gasoline, distillate, utilization):
    if fundamentals is not None:
        if isinstance(fundamentals, Mapping):
            gasoline = fundamentals.get("gasoline", fundamentals.get("gasoline_stocks", gasoline))
            distillate = fundamentals.get("distillate", fundamentals.get("distillate_stocks", distillate))
            utilization = fundamentals.get("utilization", fundamentals.get("refinery_utilization", utilization))
        elif isinstance(fundamentals, pd.DataFrame):
            aliases = {
                "gasoline": ("gasoline", "gasoline_stocks", "WGTSTUS1"),
                "distillate": ("distillate", "distillate_stocks", "WDISTUS1"),
                "utilization": ("utilization", "refinery_utilization", "WPULEUS3"),
            }
            for key, names in aliases.items():
                found = next((name for name in names if name in fundamentals), None)
                if found:
                    if key == "gasoline": gasoline = fundamentals[found]
                    elif key == "distillate": distillate = fundamentals[found]
                    else: utilization = fundamentals[found]
    if gasoline is None or distillate is None or utilization is None:
        raise ValueError("gasoline, distillate, and utilization weekly series are required")
    return gasoline, distillate, utilization


def _price_book(panel: pd.DataFrame, *, trade_bps: float, roll_bps: float, overlay: bool):
    # Import the existing engine only when an experiment is run.
    import engine_v2

    panel = panel.sort_index()
    levels = engine_v2.build_levels(panel)
    positions, gross_returns, turnover = engine_v2.build_v2(levels)
    net = engine_v2.apply_costs(
        positions, gross_returns, turnover=turnover,
        trade_bps=trade_bps, roll_bps=roll_bps,
    )
    book = net.loc[:, list(CORE3)].mean(axis=1).rename("book")
    if overlay:
        book = _apply_v2_overlay(book)
    return book, positions, gross_returns


def run_experiment(
    panel: pd.DataFrame,
    fundamentals=None,
    *,
    gasoline=None,
    distillate=None,
    utilization=None,
    permutations: int = 20,
    seed: int = 23,
    trade_bps: float = TRADE_BPS,
    roll_bps: float = ROLL_BPS,
    overlay: bool = True,
) -> dict:
    """Run baseline, physical-scale, and shuffled negative-control variants."""
    panel = panel.sort_index().copy()
    gasoline, distillate, utilization = _extract_inputs(fundamentals, gasoline, distillate, utilization)
    releases = build_fundamental_features(gasoline, distillate, utilization)
    daily = daily_feature_state(releases, panel.index)
    scale = fundamental_scale(daily)

    baseline, positions, gross = _price_book(panel, trade_bps=trade_bps, roll_bps=roll_bps, overlay=overlay)
    scaled, scaled_positions = _book_from_parts(
        positions, gross, scale=scale, index=panel.index,
        trade_bps=trade_bps, roll_bps=roll_bps, overlay=overlay,
    )
    controls = []
    control_books = []
    for i in range(permutations):
        shuffled = permute_release_features(releases, seed=seed + i)
        shuffled_daily = daily_feature_state(shuffled, panel.index)
        shuffled_scale = fundamental_scale(shuffled_daily)
        control, control_position = _book_from_parts(
            positions, gross, scale=shuffled_scale, index=panel.index,
            trade_bps=trade_bps, roll_bps=roll_bps, overlay=overlay,
        )
        control_books.append(control.rename(f"permutation_{i + 1}"))
        controls.append(_stats(control, control_position))

    analysis = slice(WARMUP, None) if len(panel) > WARMUP else slice(None)
    analysis_index = baseline.iloc[analysis].index
    baseline_position_frame = pd.DataFrame(positions).loc[analysis_index, list(CORE3)]
    baseline_stats = _stats(baseline.loc[analysis_index], positions=baseline_position_frame)
    scaled_stats = _stats(scaled.loc[analysis_index], positions=scaled_positions.loc[analysis_index])
    factor_results = {"baseline": {}, "scaled": {}}
    for name in CORE3:
        base_position = positions[name].reindex(panel.index).fillna(0.0)
        base_gross = gross[name].reindex(panel.index).fillna(0.0)
        scaled_position = scaled_positions[name]
        scaled_gross = base_gross
        if name in CRACK_FACTORS:
            scaled_gross = base_gross * scale.shift(1).fillna(1.0)
        base_net = _apply_costs(base_position, base_gross, trade_bps=trade_bps, roll_bps=roll_bps)
        scaled_net = _apply_costs(scaled_position, scaled_gross, trade_bps=trade_bps, roll_bps=roll_bps)
        factor_results["baseline"][name] = _stats(
            base_net.loc[analysis_index], positions=pd.DataFrame({name: base_position.loc[analysis_index]})
        )
        factor_results["scaled"][name] = _stats(
            scaled_net.loc[analysis_index], positions=pd.DataFrame({name: scaled_position.loc[analysis_index]})
        )
    control_frame = pd.concat(control_books, axis=1).iloc[analysis] if control_books else pd.DataFrame(index=panel.index[analysis])
    control_summary = {
        "permutations": controls,
        "mean_sharpe": float(np.nanmean([x["sharpe"] for x in controls])) if controls else np.nan,
        "std_sharpe": float(np.nanstd([x["sharpe"] for x in controls])) if controls else np.nan,
    }
    return {
        "baseline": baseline_stats,
        "scaled": scaled_stats,
        "factor_results": factor_results,
        "negative_control": control_summary,
        "baseline_returns": baseline.iloc[analysis],
        "scaled_returns": scaled.iloc[analysis],
        "negative_control_returns": control_frame,
        "release_features": releases,
        "daily_features": daily,
        "scale": scale,
        "events": {
            "releases": int(len(releases)),
            "confirmed_entries": int(
                ((scale == 1.0) & daily["physical_score"].notna()
                 & daily["product_draw_z"].notna()
                 & (scale.shift(1).fillna(0.0) != 1.0)).sum()
            ),
            "days_affected": int((scale.reindex(panel.index).fillna(1.0) != 1.0).sum()),
        },
        "control_inputs": {
            "strategy_engine": "engine_v2.build_v2",
            "strategy_parameters_fitted": False,
            "core3": list(CORE3),
            "weights": {factor: 1.0 / len(CORE3) for factor in CORE3},
            "trade_bps": trade_bps,
            "roll_bps_per_year": roll_bps,
            "release_lag_days": RELEASE_LAG_DAYS,
            "min_same_month_obs": MIN_SAME_MONTH_OBS,
            "score_cutoff": SCORE_CUTOFF,
            "product_cutoff": PRODUCT_CUTOFF,
        },
    }


def _cached_series(code: str) -> pd.Series:
    path = Path(f"/tmp/eia_{code}.csv")
    if not path.exists():
        raise FileNotFoundError(path)
    return _as_series(path, code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default="panel_v2.parquet")
    parser.add_argument("--gasoline", default="/tmp/eia_WGTSTUS1.csv")
    parser.add_argument("--distillate", default="/tmp/eia_WDISTUS1.csv")
    parser.add_argument("--utilization", default="/tmp/eia_WPULEUS3.csv")
    parser.add_argument("--permutations", type=int, default=20)
    args = parser.parse_args()
    result = run_experiment(
        pd.read_parquet(args.panel),
        gasoline=args.gasoline,
        distillate=args.distillate,
        utilization=args.utilization,
        permutations=args.permutations,
    )
    print(json.dumps({k: result[k] for k in ("baseline", "scaled", "factor_results", "negative_control", "events", "control_inputs")}, indent=2, default=str))


if __name__ == "__main__":
    main()
