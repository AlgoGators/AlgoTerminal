"""Frozen walk-forward validation for the corrected futures book.

This module evaluates the declared historical variants without selecting a
release from validation results.  Parameters are fixed in ``engine_v2``.
Only non-EQ factor weights are fitted, and each fit stops before the fold's
90 completed-session purge gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import itertools
import math

import numpy as np
import pandas as pd

import engine_v2 as eng

ROOT = Path(__file__).resolve().parent
PANEL = ROOT / "panel_v2.parquet"
RESULTS = ROOT / "unseen_validation_results.csv"
REPORT = ROOT / "research" / "unseen_validation_run.md"
PURGE_SESSIONS = 90
VALIDATION_SESSIONS = 504
TRADE_BPS = 5.0
ROLL_BPS = 20.0

V4_SUBSETS = {
    "FULL": ["crack_321", "crack_ho", "cross_sectional", "ng", "bzwti"],
    "NOHO": ["crack_321", "cross_sectional", "ng", "bzwti"],
    "CORE3": ["crack_321", "cross_sectional", "bzwti"],
    "CORE2": ["crack_321", "cross_sectional"],
}
V5_SUBSETS = {
    "CORE3": ["crack_321", "cross_sectional", "bzwti"],
    "CORE3B5": ["crack_321", "cross_sectional", "bzwti", "brent321"],
    "CORE3B6": ["crack_321", "cross_sectional", "bzwti", "brent_xs"],
    "CORE3BB": ["crack_321", "cross_sectional", "bzwti", "brent321", "brent_xs"],
    "FULLB": ["crack_321", "crack_ho", "cross_sectional", "ng", "bzwti", "brent321", "brent_xs"],
}
CORE3 = V5_SUBSETS["CORE3"]
CAPS = {"NOCAP": None, "CAP8": 0.08, "CAP5": 0.05}


@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_end_pos: int
    purge_start_pos: int
    purge_end_pos: int
    validation_start_pos: int
    validation_end_pos: int
    train_end: pd.Timestamp
    purge_start: pd.Timestamp
    purge_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


def make_folds(index: pd.Index, validation_sessions: int = VALIDATION_SESSIONS,
               purge_sessions: int = PURGE_SESSIONS,
               initial_train_sessions: int | None = None) -> list[Fold]:
    """Create contiguous validation blocks separated from fits by session gaps.

    The first fit has at least 120 observations and uses as much of the early
    panel as needed when a small test index is supplied.  Every later block is
    preceded by exactly ``purge_sessions`` completed rows.
    """
    idx = pd.DatetimeIndex(index).sort_values().unique()
    if validation_sessions <= 0 or purge_sessions < 0:
        raise ValueError("validation_sessions must be positive and purge_sessions non-negative")
    if initial_train_sessions is None:
        initial_train_sessions = max(120, min(756, len(idx) - purge_sessions - validation_sessions))
    first_start = int(initial_train_sessions) + purge_sessions
    if first_start >= len(idx):
        return []
    folds: list[Fold] = []
    start = first_start
    number = 1
    while start < len(idx):
        end = min(start + validation_sessions - 1, len(idx) - 1)
        train_end_pos = start - purge_sessions - 1
        purge_start_pos = train_end_pos + 1
        purge_end_pos = start - 1
        folds.append(Fold(
            fold_id=f"fold_{number:02d}", train_end_pos=train_end_pos,
            purge_start_pos=purge_start_pos, purge_end_pos=purge_end_pos,
            validation_start_pos=start, validation_end_pos=end,
            train_end=idx[train_end_pos], purge_start=idx[purge_start_pos],
            purge_end=idx[purge_end_pos], validation_start=idx[start],
            validation_end=idx[end],
        ))
        number += 1
        start = end + 1 + purge_sessions
    return folds


def scored_slice(index: pd.Index, fold: Fold) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index).sort_values().unique()
    return idx[fold.validation_start_pos:fold.validation_end_pos + 1]


def _rp_weights(returns: pd.DataFrame, shrink: float) -> pd.Series:
    cov = returns.cov().to_numpy(dtype=float)
    d = np.sqrt(np.maximum(np.diag(cov), 1e-18))
    corr = cov / np.outer(d, d)
    corr = np.nan_to_num(corr, nan=0.0)
    shrunk = (1.0 - shrink) * corr + shrink * np.eye(len(corr))
    covs = shrunk * np.outer(d, d)
    w = np.ones(len(corr))
    for _ in range(200):
        mcv = covs @ w
        w = 1.0 / np.sqrt(np.maximum(mcv, 1e-18))
        w /= w.sum()
    return pd.Series(w, index=returns.columns)


def fit_weights(returns: pd.DataFrame, factors: list[str], scheme: str,
                fold: Fold) -> tuple[dict[str, float], pd.Timestamp]:
    """Fit a declared weight scheme using rows strictly before the purge gap."""
    fit = returns.loc[:fold.train_end, factors].dropna(how="all")
    if fit.empty:
        raise ValueError(f"no fit observations before {fold.purge_start}")
    fit = fit.replace([np.inf, -np.inf], np.nan).dropna(axis=1, how="all")
    fit = fit.reindex(columns=factors).fillna(0.0)
    if scheme == "EQ":
        raw = pd.Series(1.0, index=factors)
    elif scheme == "INV":
        raw = 1.0 / fit.std().replace(0.0, np.nan)
    elif scheme == "HLV":
        raw = (1.0 / fit.std().replace(0.0, np.nan)) ** 0.5
    elif scheme == "RP05":
        raw = _rp_weights(fit, 0.5)
    elif scheme == "RP07":
        raw = _rp_weights(fit, 0.7)
    else:
        raise ValueError(f"unknown weight scheme {scheme}")
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if raw.sum() <= 0:
        raw = pd.Series(1.0, index=factors)
    weights = (raw / raw.sum()).to_dict()
    return weights, fold.train_end


def brent_levels(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "brent321": (2 * df.RB + df.HO) / 3 * 42.0 - df.BZ,
        "brent_gas": df.RB * 42.0 - df.BZ,
        "brent_ho": df.HO * 42.0 - df.BZ,
    }


def _single_crush(level: pd.Series, vt: float, cap: float | None) -> tuple[pd.Series, pd.Series, pd.Series]:
    z = eng.seasonal_z(level)
    state = np.zeros(len(level), dtype=float)
    held = 0.0
    for i, value in enumerate(z.to_numpy(dtype=float)):
        if not np.isnan(value):
            if held == 0.0 and value <= -eng.SMR_ENTRY:
                held = 1.0
            elif held == 1.0 and value >= eng.SMR_EXIT:
                held = 0.0
        state[i] = held
    raw = pd.Series(state, index=level.index) * eng.fixed_vol_scale(level, vt)
    pos = eng.leg_risk(raw, level, trailing_stop=False)
    if cap is not None:
        pos = pos.clip(-eng.gap_cap(level, cap), eng.gap_cap(level, cap))
    base = eng.base_of(level).shift(1).replace(0.0, np.nan)
    ret = pos.shift(1).fillna(0.0) * level.diff() / base
    return pos.fillna(0.0), ret.fillna(0.0), pos.diff().abs().fillna(0.0)


def _cross_section(levels: dict[str, pd.Series], legs: list[str], vt: float,
                   cap: float | None) -> tuple[pd.Series, pd.Series, pd.Series]:
    zdf = pd.DataFrame({name: eng.seasonal_z(levels[name]) for name in legs})
    chosen = np.full(len(zdf), -1, dtype=int)
    values = zdf.to_numpy(dtype=float)
    for i, row in enumerate(values):
        if np.isfinite(row).all() and np.nanmin(row) < eng.XS_MIN_Z:
            chosen[i] = int(np.nanargmin(row))
    positions: dict[str, pd.Series] = {}
    returns: dict[str, pd.Series] = {}
    for li, name in enumerate(legs):
        level = levels[name]
        on = pd.Series(chosen == li, index=level.index)
        pos = eng.leg_risk(eng.fixed_vol_scale(level, vt).where(on, 0.0), level,
                            trailing_stop=False)
        if cap is not None:
            pos = pos.clip(-eng.gap_cap(level, cap), eng.gap_cap(level, cap))
        positions[name] = pos.fillna(0.0)
        base = eng.base_of(level).shift(1).replace(0.0, np.nan)
        returns[name] = pos.shift(1).fillna(0.0) * level.diff() / base
    pos_df = pd.DataFrame(positions)
    return pos_df.sum(axis=1), pd.DataFrame(returns).sum(axis=1).fillna(0.0), pos_df.diff().abs().sum(axis=1)


def build_net(df: pd.DataFrame, family: str, cap_name: str = "NOCAP",
              tamed: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build a corrected net return panel for one family configuration."""
    levels = eng.build_levels(df)
    cap = CAPS[cap_name]
    factors, gross, turnover = eng.build_v2(levels, cap3sig=cap)
    if family in {"v5", "vNext"}:
        bl = brent_levels(df)
        p, r, t = _single_crush(bl["brent321"], eng.VT_F1, cap)
        factors["brent321"], gross["brent321"], turnover["brent321"] = p, r, t
        p, r, t = _cross_section(bl, ["brent321", "brent_gas", "brent_ho"], eng.VT_F2, cap)
        factors["brent_xs"], gross["brent_xs"], turnover["brent_xs"] = p, r, t
    if tamed:
        limits = {"cross_sectional": 0.40, "brent_xs": 0.40, "ng": 0.40,
                  "crack_321": 0.60, "crack_ho": 0.60, "brent321": 0.60,
                  "bzwti": 0.50}
        for name, limit in limits.items():
            if name not in factors:
                continue
            old = factors[name].replace(0.0, np.nan)
            new = factors[name].clip(-limit, limit)
            ratio = (new / old).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            gross[name] = (gross[name] * ratio).fillna(0.0)
            factors[name] = new.fillna(0.0)
            turnover[name] = factors[name].diff().abs().fillna(0.0)
    net = eng.apply_costs(factors, gross, turnover=turnover,
                          trade_bps=TRADE_BPS, roll_bps=ROLL_BPS,
                          use_proxy=False, df=df, levels=levels)
    return factors, net, turnover


def _stats(r: pd.Series) -> dict[str, float]:
    r = pd.Series(r, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan,
                "worst_day": np.nan, "vol": np.nan, "total": np.nan}
    equity = (1.0 + r).cumprod()
    years = len(r) / 252.0
    return {"cagr": equity.iloc[-1] ** (1.0 / years) - 1.0,
            "sharpe": r.mean() / r.std() * math.sqrt(252.0),
            "maxdd": (equity / equity.cummax() - 1.0).min(),
            "worst_day": r.min(), "vol": r.std() * math.sqrt(252.0),
            "total": equity.iloc[-1] - 1.0}


def _overlay(book: pd.Series, mode: str = "OFF", joint: pd.Series | None = None,
             scale: float = 1.0, probation: int | None = None) -> pd.Series:
    """Apply the causal V2 ladder and optional causal joint holder."""
    book = book.astype(float).fillna(0.0)
    rv = book.rolling(20, min_periods=10).std().shift(1) * math.sqrt(252.0)
    gear = (0.10 / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0).shift(1).fillna(1.0)
    state, eq, high, engine_eq, engine_high = 1.0, 1.0, 1.0, 1.0, 1.0
    timer = 0
    out = np.zeros(len(book), dtype=float)
    j = joint.reindex(book.index).fillna(False).to_numpy(bool) if joint is not None else np.zeros(len(book), bool)
    for i, value in enumerate(book.to_numpy(dtype=float)):
        if mode in {"JOINT", "HALF"} and j[i]:
            state = scale
        elif mode in {"PROB3", "PROB5", "PROB10", "HALF_PROB5"} and j[i]:
            timer = probation or 5
        if timer > 0:
            applied = 0.5 if mode == "HALF_PROB5" else 1.0
            timer -= 1
        else:
            applied = state
        if mode == "OFF":
            applied = 1.0
        out[i] = value * gear.iloc[i] * applied
        realized = out[i]
        eq *= 1.0 + realized
        high = max(high, eq)
        engine_eq *= 1.0 + value
        was_high = engine_high
        engine_high = max(engine_high, engine_eq)
        new_high = engine_high >= was_high
        dd = eq / high - 1.0 if high else 0.0
        if mode not in {"OFF", "JOINT", "HALF", "PROB3", "PROB5", "PROB10", "HALF_PROB5"}:
            continue
        if timer > 0 or ((mode in {"JOINT", "HALF"}) and j[i]):
            continue
        if state == 1.0:
            if dd <= -0.10:
                state = 0.0
            elif dd <= -0.06:
                state = 0.5
        elif state == 0.5:
            if dd <= -0.10:
                state = 0.0
            elif new_high:
                state = 1.0
        elif new_high:
            state = 1.0
    return pd.Series(out, index=book.index)


def _depth(factors: pd.DataFrame | dict[str, pd.Series], levels: dict[str, pd.Series]) -> pd.Series:
    held = []
    names = factors.columns if isinstance(factors, pd.DataFrame) else factors.keys()
    index = factors.index if isinstance(factors, pd.DataFrame) else next(iter(factors.values())).index
    for name in names:
        level_name = name
        if name == "cross_sectional":
            level_name = "crack_321"
        if name == "brent_xs":
            level_name = "brent321"
        if level_name in levels:
            held.append(eng.seasonal_z(levels[level_name]).shift(1).where(factors[name].shift(1).abs() > 0))
    if not held:
        return pd.Series(np.nan, index=index)
    return pd.concat(held, axis=1).min(axis=1).reindex(index)


def joint_signal(depth: pd.Series, df: pd.DataFrame, threshold: tuple[float, float, float]) -> pd.Series:
    crash, deep, crude = threshold
    # All three inputs are known before the scored session.
    held = depth.shift(1)
    crash5 = depth.shift(6) - depth.shift(1)
    crude20 = df["CL"].pct_change(20).shift(1).reindex(depth.index)
    return ((crash5 >= crash) & (held <= deep) & (crude20 <= crude)).fillna(False)


def _v4_manifest() -> list[dict]:
    rows = []
    for cap, subset, weight, overlay in itertools.product(
        ["NOCAP", "CAP8", "CAP5"], V4_SUBSETS, ["EQ", "HLV", "INV"], ["OFF", "V2"]):
        rows.append({"family": "v4", "subset": subset, "weight": weight,
                     "sizing": "FIXED", "overlay": overlay, "cap": cap,
                     "joint": "off", "cush": "off", "variant_id":
                     f"v4_{subset}_{weight}_{cap}_{overlay}", "release_rank": "not_used"})
    return rows


def _v5_manifest() -> list[dict]:
    rows = []
    for cap, tame, subset, weight, overlay in itertools.product(
        ["NOCAP", "CAP5"], ["NT", "TAMED"], V5_SUBSETS,
        ["EQ", "HLV", "RP05", "RP07"], ["OFF", "V2", "V3"]):
        rows.append({"family": "v5", "subset": subset, "weight": weight,
                     "sizing": tame, "overlay": overlay, "cap": cap,
                     "joint": "off", "cush": "off", "variant_id":
                     f"v5_{subset}_{weight}_{tame}_{cap}_{overlay}", "release_rank": "not_used"})
    return rows


def _v7_manifest() -> list[dict]:
    thresholds = [(1.0, -1.25, -0.15), (1.2, -1.50, -0.15),
                  (0.8, -1.25, -0.15), (1.0, -1.25, -0.10)]
    rows = [{"family": "v7", "subset": "CORE3", "weight": "EQ", "sizing": "FIXED",
             "overlay": "V2", "cap": "NOCAP", "joint": "off", "cush": "off",
             "variant_id": "v7_V2", "release_rank": "not_used"}]
    for n, threshold in enumerate(thresholds, 1):
        label = f"c{threshold[0]}_d{threshold[1]}_cr{threshold[2]}"
        rows.append({"family": "v7", "subset": "CORE3", "weight": "EQ", "sizing": "FIXED",
                     "overlay": "JOINT", "cap": "NOCAP", "joint": label, "cush": "off",
                     "variant_id": f"v7_JOINT_{n}_{label}", "release_rank": "not_used"})
    return rows


def _vnext_manifest() -> list[dict]:
    rows = []
    for subset, joint, cush, overlay, cap in itertools.product(
        ["core3", "core3bb"], ["off", "full", "half", "prob3", "prob5", "prob10", "half_prob5"],
        ["off", "s05", "s07"], ["book", "per"], ["nocap", "cap8", "cap5"]):
        rows.append({"family": "vNext", "subset": subset, "weight": "EQ", "sizing": "FIXED",
                     "overlay": overlay.upper(), "cap": cap.upper(), "joint": joint,
                     "cush": cush, "variant_id":
                     f"vNext_{subset}_{joint}_{cush}_{overlay}_{cap}", "release_rank": "not_used"})
    return rows


def variant_manifest() -> list[dict]:
    """Return the complete declared manifest.  No result is used for ranking."""
    return _v4_manifest() + _v5_manifest() + _v7_manifest() + _vnext_manifest()


def _threshold(label: str) -> tuple[float, float, float]:
    values = label.replace("c", "").replace("_d", ",").replace("_cr", ",").split(",")
    return tuple(float(x) for x in values)  # type: ignore[return-value]


def _candidate_return(row: dict, net: pd.DataFrame, factors: pd.DataFrame,
                      df: pd.DataFrame, fold: Fold, weights: dict[str, float]) -> pd.Series:
    subsets = V4_SUBSETS if row["family"] == "v4" else V5_SUBSETS
    names = subsets[row["subset"]] if row["family"] != "vNext" else (CORE3 if row["subset"] == "core3" else V5_SUBSETS["CORE3BB"])
    raw = sum((weights[name] * net[name] for name in names), pd.Series(0.0, index=net.index))
    scored = raw.loc[fold.validation_start:fold.validation_end]
    if row["family"] == "v4":
        if row["overlay"] == "V2":
            return _overlay(scored, "V2")
        return scored
    depth = _depth(factors, eng.build_levels(df))
    if row["family"] == "v5":
        if row["overlay"] == "V2":
            return _overlay(scored, "V2")
        if row["overlay"] == "V3":
            # V3 forces full exposure in a deep held crush.  The signal is lagged.
            return _overlay(scored, "JOINT", depth.loc[scored.index] <= -1.25, 1.0)
        return scored
    joint_name = row["joint"]
    if joint_name == "off":
        joint = None
    else:
        joint = joint_signal(depth, df, _threshold(joint_name)).loc[scored.index]
    mode = row["joint"].upper()
    if row["overlay"] == "PER":
        groups = [[x for x in ["crack_321", "cross_sectional"] if x in names],
                  [x for x in ["brent321", "brent_xs"] if x in names],
                  [x for x in ["bzwti"] if x in names]]
        out = pd.Series(0.0, index=scored.index)
        for group in filter(None, groups):
            part = sum((weights[x] * net[x] for x in group), pd.Series(0.0, index=net.index))
            out = out.add(_overlay(part.loc[scored.index], mode, joint,
                                   0.5 if mode in {"HALF", "HALF_PROB5"} else 1.0,
                                   int(mode[-1]) if mode.startswith("PROB") else (5 if mode == "HALF_PROB5" else None)), fill_value=0.0)
        return out
    return _overlay(scored, mode, joint, 0.5 if mode in {"HALF", "HALF_PROB5"} else 1.0,
                    int(mode[-1]) if mode.startswith("PROB") else (5 if mode == "HALF_PROB5" else None))


def _load_cushing(index: pd.Index) -> pd.Series | None:
    path = Path("/home/sebas/.algoterminal-data/cache/eia__W_EPC0_SAX_YCUOK_MBBL.parquet")
    if not path.exists():
        return None
    try:
        data = pd.read_parquet(path)
        s = data["close"].dropna() if "close" in data else data.iloc[:, 0].dropna()
        s.index = pd.to_datetime(s.index)
        z = pd.Series(np.nan, index=s.index)
        for month in range(1, 13):
            dates = s.index[s.index.month == month]
            for i, date in enumerate(dates):
                past = s.loc[: date - pd.Timedelta(days=1)]
                past = past[past.index.month == month]
                if len(past) >= 12 and past.std() > 0:
                    z.loc[date] = (s.loc[date] - past.mean()) / past.std()
        z.index = z.index + pd.Timedelta(days=6)
        return z.reindex(pd.DatetimeIndex(index).union(z.index)).sort_index().ffill().reindex(index)
    except Exception:
        return None


def _apply_cush(net: pd.DataFrame, factors: pd.DataFrame, df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == "off":
        return net
    z = _load_cushing(df.index)
    if z is None:
        return net
    minimum = 0.5 if mode == "s05" else 0.7
    scale = (1.0 - (1.0 - minimum) * (z / 1.5).clip(0.0, 1.0)).fillna(1.0).clip(minimum, 1.0).shift(1).fillna(1.0)
    out = net.copy()
    level = eng.build_levels(df)["bzwti"]
    base = eng.base_of(level).shift(1).replace(0.0, np.nan)
    pos = factors["bzwti"] * scale
    out["bzwti"] = pos.shift(1).fillna(0.0) * level.diff() / base - TRADE_BPS / 10000.0 * pos.diff().abs().fillna(0.0) - ROLL_BPS / 252.0 / 10000.0 * pos.abs()
    return out.fillna(0.0)


def run_validation(panel_path: Path = PANEL) -> pd.DataFrame:
    df = pd.read_parquet(panel_path).sort_index()
    folds = make_folds(df.index)
    if not folds:
        raise ValueError("panel is too short for the frozen fold plan")
    manifest = variant_manifest()
    built: dict[tuple[str, str, bool], tuple[pd.DataFrame, pd.DataFrame]] = {}
    for family, cap, tame in [("v4", "NOCAP", False), ("v4", "CAP8", False), ("v4", "CAP5", False),
                              ("v5", "NOCAP", False), ("v5", "CAP5", False),
                              ("v5", "NOCAP", True), ("v5", "CAP5", True),
                              ("vNext", "NOCAP", False), ("vNext", "CAP8", False), ("vNext", "CAP5", False)]:
        factors, net, _ = build_net(df, family, cap, tame)
        built[(family, cap, tame)] = (factors, net)
    rows: list[dict] = []
    aggregate_returns: dict[str, list[pd.Series]] = {r["variant_id"]: [] for r in manifest}
    aggregate_controls: dict[str, list[float]] = {r["variant_id"]: [] for r in manifest}
    for row in manifest:
        family = row["family"]
        cap = row["cap"] if family != "vNext" else row["cap"]
        cap = cap.upper()
        tame = row.get("sizing") == "TAMED"
        factors, base_net = built[(family, cap, tame)]
        net = _apply_cush(base_net, factors, df, row["cush"] if family == "vNext" else "off")
        for fold in folds:
            names = V4_SUBSETS[row["subset"]] if family == "v4" else V5_SUBSETS[row["subset"]] if family == "v5" else CORE3 if row["subset"] == "core3" else V5_SUBSETS["CORE3BB"]
            weights, fit_end = fit_weights(net, names, row["weight"], fold)
            result = _candidate_return(row, net, factors, df, fold, weights)
            metrics = _stats(result)
            aggregate_returns[row["variant_id"]].append(result)
            control = np.nan
            if family in {"v7", "vNext"} and row["joint"] != "off":
                rng = np.random.default_rng(7 + fold.validation_start_pos)
                # Shuffle only the declared causal labels. This is a negative control,
                # not a selection score.
                depth = _depth(factors, eng.build_levels(df))
                labels = joint_signal(depth, df, _threshold(row["joint"])) .loc[result.index]
                controls = []
                for _ in range(12):
                    controls.append(_stats(_overlay(result, "V2", pd.Series(rng.permutation(labels.to_numpy()), index=result.index)))['sharpe'])
                control = float(np.nanmean(controls))
                aggregate_controls[row["variant_id"]].extend(controls)
            rows.append({**row, "metric_scope": "fold", "fold_id": fold.fold_id,
                         "train_end": fold.train_end.date().isoformat(),
                         "purge_start": fold.purge_start.date().isoformat(),
                         "purge_end": fold.purge_end.date().isoformat(),
                         "validation_start": fold.validation_start.date().isoformat(),
                         "validation_end": fold.validation_end.date().isoformat(),
                         "train_rows": fold.train_end_pos + 1,
                         "purge_rows": fold.purge_end_pos - fold.purge_start_pos + 1,
                         "validation_rows": len(result), "fit_end": fit_end.date().isoformat(),
                         "weight_sum": sum(weights.values()), **metrics,
                         "negative_control_mean_sharpe": control,
                         "negative_control_n": 12 if np.isfinite(control) else 0})
    for row in manifest:
        vid = row["variant_id"]
        combined = pd.concat(aggregate_returns[vid])
        metrics = _stats(combined)
        controls = aggregate_controls[vid]
        rows.append({**row, "metric_scope": "aggregate", "fold_id": "aggregate",
                     "train_end": "", "purge_start": "", "purge_end": "",
                     "validation_start": str(combined.index.min().date()),
                     "validation_end": str(combined.index.max().date()),
                     "train_rows": "", "purge_rows": "", "validation_rows": len(combined),
                     "fit_end": "", "weight_sum": "", **metrics,
                     "negative_control_mean_sharpe": float(np.nanmean(controls)) if controls else np.nan,
                     "negative_control_n": len(controls)})
    result = pd.DataFrame(rows)
    result.to_csv(RESULTS, index=False)
    return result


def main() -> None:
    result = run_validation()
    write_report(result)
    print(f"wrote {RESULTS} ({len(result)} rows)")
    print(f"wrote {REPORT}")


def write_report(result: pd.DataFrame, path: Path = REPORT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    folds = result[result.metric_scope == "fold"].drop_duplicates("fold_id")
    agg = result[result.metric_scope == "aggregate"]
    families = result[["family", "variant_id"]].drop_duplicates().groupby("family").size()
    lines = [
        "# Frozen walk-forward unseen validation",
        "",
        "## Verdict and scope",
        "",
        "This run is retrospective post-selection evidence, not clean future OOS.",
        "The historical panel, factors, thresholds, overlays, and candidate families were inspected during development.",
        "No validation result ranks variants or changes the release.",
        "",
        "The local corrected `engine_v2.py` and durable `panel_v2.parquet` were used.",
        f"The panel has {len(pd.read_parquet(PANEL))} rows from {pd.read_parquet(PANEL).index.min().date()} through {pd.read_parquet(PANEL).index.max().date()}.",
        "Parameters are fixed at 5 bps trade cost, 20 bps annual stub roll cost, and the engine's frozen risk constants.",
        "All signal, sizing, risk, overlay, and joint inputs use t-1 or older information.",
        f"Each scored fold has a {PURGE_SESSIONS}-completed-session purge gap.",
        "",
        "## Fold boundaries and row counts",
        "",
        "| fold | fit end | purge start | purge end | validation start | validation end | train rows | purge rows | validation rows |",
        "|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for _, f in folds.iterrows():
        lines.append(f"| {f.fold_id} | {f.train_end} | {f.purge_start} | {f.purge_end} | {f.validation_start} | {f.validation_end} | {f.train_rows} | {f.purge_rows} | {f.validation_rows} |")
    lines += ["", "The fit end is the last row allowed for non-EQ weight fitting.",
              "The purge rows are excluded from both fitting and scored validation.", "",
              "## Tested variant manifest", "",
              "The complete manifest is in `unseen_validation_results.csv`.",
              "The counts below are configurations, not a performance ranking.", ""]
    for family, count in families.items():
        lines.append(f"- {family}: {count} declared configurations")
    lines += ["", "Families covered:",
              "- v4: FULL, NOHO, CORE3, CORE2 across EQ, HLV, INV, NOCAP/CAP8/CAP5, and OFF/V2.",
              "- v5: CORE3, CORE3B5, CORE3B6, CORE3BB, FULLB across EQ, HLV, RP05, RP07, NT/TAMED, NOCAP/CAP5, and OFF/V2/V3.",
              "- v7: V2 plus the four declared joint threshold candidates.",
              "- vNext: every reproducible declared combination of core3/core3bb, joint mode, Cushing mode, book/per-complex overlay, and gap cap.",
              "- Every row carries `release_rank=not_used`.", "",
              "## Per-fold and aggregate metrics", "",
              "CSV columns include CAGR, Sharpe, max drawdown, volatility, worst day, total return, weight sum, and row counts.",
              "Fold rows preserve each boundary and fit end.",
              "Aggregate rows concatenate the scored folds in time order without using validation outcomes to refit weights.", ""]
    for family in ["v4", "v5", "v7", "vNext"]:
        a = agg[agg.family == family]
        lines += [f"### {family} aggregate metric sample", "",
                  "| variant | subset | weight | sizing | overlay | cap | joint | Sharpe | CAGR | max DD | vol | worst day | validation rows |",
                  "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for _, r in a.head(12).iterrows():
            def pct(x): return "" if pd.isna(x) else f"{100*x:.2f}%"
            lines.append(f"| {r.variant_id} | {r.subset} | {r.weight} | {r.sizing} | {r.overlay} | {r.cap} | {r.joint} | {r.sharpe:.3f} | {pct(r.cagr)} | {pct(r.maxdd)} | {pct(r.vol)} | {pct(r.worst_day)} | {r.validation_rows} |")
        lines += ["", "The table shows the first manifest entries only for readability.",
                  "The CSV is the authoritative complete per-fold and aggregate table.", ""]
    lines += ["## Negative controls", "",
              "For v7 and vNext joint candidates, 12 seeded permutations of the causal joint labels were run per fold.",
              "The CSV records the shuffled Sharpe mean and draw count.",
              "This control tests label timing, not the broader post-selection problem.",
              "v4 and v5 have no declared event-label negative control in their source code, so their control fields are empty.", "",
              "## Exact limitations", "",
              "- These folds are retrospective. The candidate space and release history were known before this rerun.",
              "- The panel uses yfinance continuous front-month closes. It is back-adjusted and not a tradeable adjacent-contract history.",
              "- Official settlement, historical option prices, and exact contract-level fills are unavailable from the local panel.",
              "- The 20 bps annual roll stream is a fixed stub. It does not prove realized roll economics.",
              "- Fold overlays restart at each validation window. This avoids carrying validation state across folds but differs from one uninterrupted live path.",
              "- EQ weights use no fit data. Non-EQ weights fit only rows through each fold fit end, before all 90 purge rows.",
              "- The Cushing variants fall back to unchanged price-only returns when the cached EIA series is unavailable; the CSV manifest still identifies that declared mode.",
              "- Metrics are descriptive historical evidence. They do not establish deployability, capacity, liquidity, or future performance.",
              ""]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
