"""Causal weather-gate experiment on the corrected local CORE3 engine."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

import engine_v2

CORE3 = ("crack_321", "cross_sectional", "bzwti")
WEATHER_FACTORS = ("ng", "crack_ho")
CITIES = ("NYC", "HOUSTON")
DEFAULT_PANEL = Path(__file__).with_name("panel_v2.parquet")
DEFAULT_CACHE = Path.home() / ".algoterminal-data" / "cache"
DEFAULT_REPORT = Path(__file__).with_name("research") / "weather_run.md"
WEATHER_MIN_OBS = 12
WEATHER_BASE_C = 18.0
WEATHER_ROLLING_DAYS = 7
WEATHER_THRESHOLD = -1.0
WEATHER_REENTER = -0.5
PERMUTATIONS = 12
PERMUTATION_SEED = 11


def _series(value, name: str, *, dropna: bool = True) -> pd.Series:
    if isinstance(value, (str, Path)):
        frame = pd.read_parquet(value) if str(value).endswith(".parquet") else pd.read_csv(value, index_col=0, parse_dates=True)
        value = frame["close"] if "close" in frame else frame.iloc[:, 0]
    elif isinstance(value, pd.DataFrame):
        value = value["close"] if "close" in value else value.iloc[:, 0]
    if not isinstance(value, pd.Series):
        value = pd.Series(value, name=name)
    out = pd.to_numeric(value, errors="coerce").copy()
    if dropna:
        out = out.dropna()
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out[~out.index.duplicated(keep="last")].sort_index().rename(name)


def load_weather(city: str, cache_dir: str | Path = DEFAULT_CACHE) -> pd.Series:
    """Load cached NASA POWER daily T2M for a registered city."""
    key = city.upper()
    if key not in CITIES:
        raise ValueError(f"unsupported city: {city}")
    path = Path(cache_dir) / f"nasa-power__{key}.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    return _series(path, f"{key}_T2M")


def hdd_z(
    temperature: pd.Series | pd.DataFrame | str | Path,
    *,
    min_obs: int = WEATHER_MIN_OBS,
    base_c: float = WEATHER_BASE_C,
    rolling_days: int = WEATHER_ROLLING_DAYS,
) -> pd.Series:
    """Build the pre-registered causal same-month HDD z-score."""
    if min_obs < 1 or rolling_days < 1:
        raise ValueError("min_obs and rolling_days must be positive")
    t2m = _series(temperature, "T2M")
    hdd = (base_c - t2m).clip(lower=0.0)
    hdd7 = hdd.rolling(rolling_days, min_periods=3).mean()
    out = pd.Series(np.nan, index=hdd7.index, dtype=float)
    for month in range(1, 13):
        values = hdd7[hdd7.index.month == month]
        prior = values.shift(1)
        mean = prior.expanding(min_periods=min_obs).mean()
        std = prior.expanding(min_periods=min_obs).std()
        valid = std.gt(1e-12)
        out.loc[values.index] = ((values - mean) / std).where(valid)
    return out.clip(-8.0, 8.0).rename("hdd_z")


def gate_state(z: pd.Series, threshold: float = WEATHER_THRESHOLD, reenter: float = WEATHER_REENTER) -> pd.Series:
    """Return exposure state with every weather decision delayed one day."""
    values = _series(z, "hdd_z", dropna=False)
    state = 1.0
    states = []
    for value in values.to_numpy(dtype=float):
        if not np.isnan(value):
            if state == 1.0 and value < threshold:
                state = 0.0
            elif state == 0.0 and value >= reenter:
                state = 1.0
        states.append(state)
    return pd.Series(states, index=values.index, name="weather_state").shift(1).fillna(1.0)


def permute_weather_z(z: pd.Series, seed: int) -> pd.Series:
    """Shuffle weather values while retaining their dates for a control."""
    values = _series(z, "hdd_z", dropna=False)
    permutation = np.random.default_rng(seed).permutation(len(values))
    return pd.Series(values.to_numpy()[permutation], index=values.index, name=values.name)


def _overlay(book: pd.Series) -> pd.Series:
    """Apply the fixed v2 drawdown and volatility overlay."""
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
        prior_high = engine_high_water
        engine_high_water = max(engine_high_water, engine_equity)
        new_high = engine_equity >= prior_high
        if new_high:
            state = 1.0
        elif experienced_dd <= -0.10:
            state = 0.0
        elif experienced_dd <= -0.06:
            state = 0.5
    return book * pd.Series(scale, index=book.index) * gear


def _stats(returns: pd.Series) -> dict[str, float | int]:
    values = returns.dropna()
    if len(values) == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "vol": np.nan, "worst_day": np.nan, "days": 0}
    equity = (1.0 + values).cumprod()
    years = len(values) / 252.0
    std = values.std()
    return {
        "cagr": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
        "sharpe": float(values.mean() / std * np.sqrt(252)) if std else 0.0,
        "maxdd": float((equity / equity.cummax() - 1.0).min()),
        "vol": float(std * np.sqrt(252)) if std else 0.0,
        "worst_day": float(values.min()),
        "days": int(len(values)),
    }


def _window(returns: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    selected = returns.loc[start:end]
    return selected.iloc[engine_v2.WARMUP:] if len(selected) > engine_v2.WARMUP else selected


def _book(net: pd.DataFrame, factors: tuple[str, ...], overlay: bool) -> pd.Series:
    result = net.loc[:, list(factors)].mean(axis=1).rename("book")
    return _overlay(result) if overlay else result


def _gated_net(
    positions: Mapping[str, pd.Series],
    gross: Mapping[str, pd.Series],
    index: pd.Index,
    gates: Mapping[str, pd.Series],
    *,
    trade_bps: float,
    roll_bps: float,
) -> pd.DataFrame:
    gated_positions = {name: value.reindex(index).fillna(0.0).copy() for name, value in positions.items()}
    gated_gross = {name: value.reindex(index).fillna(0.0).copy() for name, value in gross.items()}
    turnover = {}
    for name, gate in gates.items():
        aligned = gate.reindex(index).ffill().fillna(1.0)
        gated_positions[name] = gated_positions[name] * aligned
        gated_gross[name] = gated_gross[name] * aligned.shift(1).fillna(1.0)
        turnover[name] = gated_positions[name].diff().abs()
    return engine_v2.apply_costs(
        gated_positions,
        gated_gross,
        turnover=turnover,
        trade_bps=trade_bps,
        roll_bps=roll_bps,
    )


def _weather_inputs(weather_data, cache_dir: Path) -> dict[str, pd.Series]:
    result = {}
    for city in CITIES:
        if weather_data is not None and city in weather_data:
            result[city] = _series(weather_data[city], f"{city}_T2M")
        else:
            result[city] = load_weather(city, cache_dir)
    return result


def run_experiment(
    panel: pd.DataFrame | str | Path = DEFAULT_PANEL,
    *,
    cache_dir: str | Path = DEFAULT_CACHE,
    weather_data: Mapping[str, object] | None = None,
    permutations: int = PERMUTATIONS,
    seed: int = PERMUTATION_SEED,
    threshold: float = WEATHER_THRESHOLD,
    reenter: float = WEATHER_REENTER,
    trade_bps: float = engine_v2.TRADE_BPS,
    roll_bps: float = engine_v2.ROLL_BPS,
    overlay: bool = True,
) -> dict:
    """Run frozen CORE3, gated additions, robustness, and shuffled controls."""
    if permutations < 0:
        raise ValueError("permutations must be non-negative")
    frame = pd.read_parquet(panel) if isinstance(panel, (str, Path)) else panel.copy()
    frame = frame.sort_index()
    levels = engine_v2.build_levels(frame)
    positions, gross, turnover = engine_v2.build_v2(levels)
    baseline_net = engine_v2.apply_costs(
        positions, gross, turnover=turnover, trade_bps=trade_bps, roll_bps=roll_bps
    )
    weather = _weather_inputs(weather_data, Path(cache_dir))
    zscores = {city: hdd_z(series) for city, series in weather.items()}
    states = {city: gate_state(z, threshold, reenter) for city, z in zscores.items()}

    def variant(city: str | None, factors: tuple[str, ...], gated_factors: tuple[str, ...] = ()):
        gates = {name: states[city] for name in gated_factors} if city else {}
        net = _gated_net(positions, gross, frame.index, gates, trade_bps=trade_bps, roll_bps=roll_bps) if gates else baseline_net
        return _book(net, factors, overlay), net

    books = {}
    combos = {
        "CORE3": (CORE3, ()),
        "CORE3+NGW": (CORE3 + ("ng",), ("ng",)),
        "CORE3+HOW": (CORE3 + ("crack_ho",), ("crack_ho",)),
        "CORE3+NGW+HOW": (CORE3 + WEATHER_FACTORS, WEATHER_FACTORS),
    }
    for name, (factors, gated_factors) in combos.items():
        city = "NYC" if gated_factors else None
        book, _ = variant(city, factors, gated_factors)
        books[name] = {
            "factors": list(factors),
            "is": _stats(_window(book, engine_v2.IS_START, frame.index.max())),
            "oos": _stats(_window(book, engine_v2.OOS_START, engine_v2.IS_START)),
        }

    factor_results = {}
    for factor in WEATHER_FACTORS:
        raw = baseline_net[factor]
        factor_results[factor] = {"raw": {"is": _stats(_window(raw, engine_v2.IS_START, frame.index.max())), "oos": _stats(_window(raw, engine_v2.OOS_START, engine_v2.IS_START))}}
        for city in CITIES:
            net = _gated_net(positions, gross, frame.index, {factor: states[city]}, trade_bps=trade_bps, roll_bps=roll_bps)
            gated = net[factor]
            factor_results[factor][city] = {
                "is": _stats(_window(gated, engine_v2.IS_START, frame.index.max())),
                "oos": _stats(_window(gated, engine_v2.OOS_START, engine_v2.IS_START)),
                "exposure_days": int((_window(gated, engine_v2.OOS_START, engine_v2.IS_START) != 0.0).sum()),
            }

    threshold_sweep = {}
    for cutoff in (-0.75, -1.0, -1.5):
        z = zscores["NYC"]
        state = gate_state(z, cutoff, reenter)
        net = _gated_net(positions, gross, frame.index, {"ng": state}, trade_bps=trade_bps, roll_bps=roll_bps)
        book = _book(net, CORE3 + ("ng",), overlay)
        threshold_sweep[str(cutoff)] = _stats(_window(book, engine_v2.OOS_START, engine_v2.IS_START))

    city_robustness = {}
    for city in CITIES:
        city_robustness[city] = {}
        for factor, suffix in (("ng", "NGW"), ("crack_ho", "HOW")):
            net = _gated_net(positions, gross, frame.index, {factor: states[city]}, trade_bps=trade_bps, roll_bps=roll_bps)
            book = _book(net, CORE3 + (factor,), overlay)
            city_robustness[city][suffix] = _stats(_window(book, engine_v2.OOS_START, engine_v2.IS_START))

    controls = []
    for control_i in range(permutations):
        shuffled = permute_weather_z(zscores["NYC"], seed + control_i)
        state = gate_state(shuffled, threshold, reenter)
        net = _gated_net(positions, gross, frame.index, {"ng": state}, trade_bps=trade_bps, roll_bps=roll_bps)
        book = _book(net, CORE3 + ("ng",), overlay)
        controls.append(_stats(_window(book, engine_v2.OOS_START, engine_v2.IS_START)))
    control_sharpes = [item["sharpe"] for item in controls]
    real_ng = books["CORE3+NGW"]["oos"]
    return {
        "data": {
            "panel_rows": int(len(frame)),
            "panel_start": str(frame.index.min().date()),
            "panel_end": str(frame.index.max().date()),
            "weather": {city: {"rows": int(len(series)), "start": str(series.index.min().date()), "end": str(series.index.max().date()), "missing_tail_days": max(0, int((frame.index.max() - series.index.max()).days))} for city, series in weather.items()},
        },
        "books": books,
        "factor_results": factor_results,
        "threshold_sweep": threshold_sweep,
        "city_robustness": city_robustness,
        "negative_control": {
            "permutations": permutations,
            "seed": seed,
            "results": controls,
            "mean_sharpe": float(np.mean(control_sharpes)) if control_sharpes else np.nan,
            "std_sharpe": float(np.std(control_sharpes)) if control_sharpes else np.nan,
            "min_sharpe": float(np.min(control_sharpes)) if control_sharpes else np.nan,
            "max_sharpe": float(np.max(control_sharpes)) if control_sharpes else np.nan,
            "real_sharpe": real_ng["sharpe"],
        },
        "control_inputs": {
            "engine": "engine_v2.build_v2",
            "strategy_parameters_fitted": False,
            "core3": list(CORE3),
            "weights": {factor: 1.0 / len(CORE3) for factor in CORE3},
            "weather_factors": list(WEATHER_FACTORS),
            "weather_base_c": WEATHER_BASE_C,
            "hdd_rolling_days": WEATHER_ROLLING_DAYS,
            "same_month_min_obs": WEATHER_MIN_OBS,
            "threshold": threshold,
            "reenter": reenter,
            "trade_bps": trade_bps,
            "roll_bps_per_year": roll_bps,
            "warmup_days": engine_v2.WARMUP,
            "overlay_v2": overlay,
        },
    }


def _pct(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value * 100:.4f}%"


def _num(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:.4f}"


def render_report(result: dict) -> str:
    data = result["data"]
    controls = result["negative_control"]
    lines = [
        "# Weather experiment",
        "",
        "## Scope and preregistered rule",
        "",
        "The pre-registered hypothesis was that unusually warm weather weakens the demand driver for NG and winter-distillate crack longs.",
        "The gate uses seven-day mean HDD, with HDD equal to `max(0, 18 C - T2M)`.",
        "Each value is compared with prior same-month observations after at least 12 observations.",
        "The score is clipped to `[-8, 8]`.",
        "Exposure turns off below z `-1.0` and re-enters at z `-0.5`.",
        "The state is applied on the next day.",
        "",
        "The corrected local engine is `engine_v2.build_v2`.",
        f"The fixed CORE3 is `{', '.join(CORE3)}` with equal one-third weights.",
        "The run uses 5 bps trade costs, 20 bps annual roll drag, a 90-day warmup, and the fixed v2 overlay.",
        "No strategy parameter was fitted in this run.",
        "",
        "## Inputs",
        "",
        f"The price panel has {data['panel_rows']} rows from {data['panel_start']} through {data['panel_end']}.",
    ]
    for city, info in data["weather"].items():
        lines.append(f"The cached NASA POWER `{city}` file has {info['rows']} usable rows from {info['start']} through {info['end']}.")
        if info["missing_tail_days"]:
            lines.append(f"The cache has no usable `{city}` T2M for the final {info['missing_tail_days']} calendar days of the panel; the last known gate state is carried forward on those dates.")
    lines += ["The requested cached files are present.", "The final cache tail is a documented input gap for the last 10 panel calendar days and does not affect the OOS window.", "", "## Book results", "", "| Variant | IS Sharpe | OOS Sharpe | OOS CAGR | OOS max drawdown | OOS volatility | Worst day |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, row in result["books"].items():
        oos = row["oos"]
        lines.append(f"| {name} | {_num(row['is']['sharpe'])} | {_num(oos['sharpe'])} | {_pct(oos['cagr'])} | {_pct(oos['maxdd'])} | {_pct(oos['vol'])} | {_pct(oos['worst_day'])} |")
    lines += ["", "## Weather-factor results", "", "| Factor | City | IS Sharpe | OOS Sharpe | OOS CAGR | OOS max drawdown | OOS exposure days |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for factor, cities in result["factor_results"].items():
        raw = cities["raw"]
        lines.append(f"| `{factor}` | raw | {_num(raw['is']['sharpe'])} | {_num(raw['oos']['sharpe'])} | {_pct(raw['oos']['cagr'])} | {_pct(raw['oos']['maxdd'])} | n/a |")
        for city in CITIES:
            row = cities[city]
            lines.append(f"| `{factor}` | {city} gate | {_num(row['is']['sharpe'])} | {_num(row['oos']['sharpe'])} | {_pct(row['oos']['cagr'])} | {_pct(row['oos']['maxdd'])} | {row['exposure_days']} |")
    lines += ["", "## Threshold plateau check", "", "| NYC NG gate threshold | OOS Sharpe | OOS CAGR | OOS max drawdown |", "| ---: | ---: | ---: | ---: |"]
    for threshold, row in result["threshold_sweep"].items():
        lines.append(f"| {threshold} | {_num(row['sharpe'])} | {_pct(row['cagr'])} | {_pct(row['maxdd'])} |")
    lines += ["", "## City robustness", "", "| City | CORE3+NGW OOS Sharpe | CORE3+HOW OOS Sharpe | NGW OOS CAGR | HOW OOS CAGR |", "| --- | ---: | ---: | ---: | ---: |"]
    for city, rows in result["city_robustness"].items():
        lines.append(f"| {city} | {_num(rows['NGW']['sharpe'])} | {_num(rows['HOW']['sharpe'])} | {_pct(rows['NGW']['cagr'])} | {_pct(rows['HOW']['cagr'])} |")
    lines += ["", "## Seeded shuffled controls", "", f"The control shuffles the NYC z-score values with seed sequence `{controls['seed']}..{controls['seed'] + controls['permutations'] - 1}` while retaining dates.", "", "| Statistic | Value |", "| --- | ---: |", f"| Real NYC CORE3+NGW OOS Sharpe | {_num(controls['real_sharpe'])} |", f"| Shuffled mean Sharpe | {_num(controls['mean_sharpe'])} |", f"| Shuffled Sharpe standard deviation | {_num(controls['std_sharpe'])} |", f"| Shuffled minimum Sharpe | {_num(controls['min_sharpe'])} |", f"| Shuffled maximum Sharpe | {_num(controls['max_sharpe'])} |"]
    lines += ["", "## Interpretation and blockers", "", "The exact result is the comparison in the tables above.", "A weather construction is not supported as an enhancer when its gated OOS result does not beat the fixed price-only comparison and its real result is not separated from the shuffled controls.", "The cached weather input is available and causal, so this run has no requested data blocker.", "The remaining data limitation is the local panel's documented yfinance continuous front-month prices and proxy roll model, not the weather files.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    args = parser.parse_args()
    result = run_experiment(args.panel, cache_dir=args.cache_dir, permutations=args.permutations)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(result), encoding="utf-8")
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
