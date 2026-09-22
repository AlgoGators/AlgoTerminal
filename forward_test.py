"""

"AUDIT NOTE (2026-09-22): this module is SUPERSEDED and CONTAMINATED.

It runs on panel_v2.parquet (yfinance raw front-month, NOT back-adjusted),
whose roll gaps were booked as price moves, and it hardcodes 5 bps/side
when the measured real cost is 16.2-24.0 bps/side. It refuses to run unless
I_ACKNOWLEDGE_CONTAMINATED_FORWARD=1. Use forward_protocol_v3.md in
algoterminal-strategy-v2 instead.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

import book_oos_v4 as book
import engine_v2 as engine


ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT / "research" / "forward_test_protocol.md"
PANEL = ROOT / "panel_v2.parquet"
FACTORS = ("crack_321", "cross_sectional", "bzwti")
INSTRUMENT_MAP = {"CL": "CL=F", "BZ": "BZ=F", "RB": "RB=F", "HO": "HO=F", "NG": "NG=F"}
PARAMETERS = {
    "factors": list(FACTORS),
    "factor_weights": {name: 1.0 / 3.0 for name in FACTORS},
    "trade_bps": 5.0,
    "roll_bps_annual": 20.0,
    "seasonal_z_lookback": 90,
    "volatility_lookback": 20,
    "volatility_target": 0.10,
    "max_factor_leverage": 1.0,
    "daily_circuit_breaker_sigma": 3.0,
    "hard_stop_pct": 0.20,
    "cooldown_sessions": 5,
    "overlay_cut_drawdown": -0.06,
    "overlay_halt_drawdown": -0.10,
    "gap_cap": None,
}


class ManifestError(ValueError):
    """The release manifest is missing, changed, or malformed."""


class LedgerError(ValueError):
    """An append-only paper ledger operation is invalid."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_versions() -> dict[str, str]:
    names = ("numpy", "pandas", "pyarrow", "pytest")
    return {name: importlib.metadata.version(name) for name in names if _has_package(name)}


def _has_package(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def _file_entry(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ManifestError(f"manifest input does not exist: {path}")
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def create_manifest(
    manifest_path: str | Path,
    *,
    panel_path: str | Path = PANEL,
    release_id: str | None = None,
    source_paths: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    """Create a release manifest once and refuse to replace an existing one."""
    target = Path(manifest_path).resolve()
    if target.exists():
        raise ManifestError(f"manifest is immutable: {target}")
    panel_path = Path(panel_path).resolve()
    required = [ROOT / "forward_test.py", ROOT / "engine_v2.py", ROOT / "book_oos_v4.py",
                ROOT / "factor_book.py", PROTOCOL, panel_path]
    if source_paths:
        required.extend(Path(item) for item in source_paths)
    paths = []
    seen: set[Path] = set()
    for item in required:
        path = item.resolve()
        if path not in seen:
            paths.append(path)
            seen.add(path)
    files = {str(path): _file_entry(path) for path in paths}
    payload: dict[str, Any] = {
        "schema": "frozen-forward-test/v1",
        "release_id": release_id or "release-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": files,
        "panel_path": str(panel_path),
        "python": sys.version,
        "python_executable": sys.executable,
        "packages": _package_versions(),
        "os": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "instrument_map": INSTRUMENT_MAP,
        "parameters": PARAMETERS,
        "calendar": {"session_labels": "panel index", "timezone": "UTC", "missing_data_policy": "flatten"},
        "execution": {"price_field": "Close", "adjustment": "continuous panel as supplied", "currency": "USD", "starting_equity": 1.0},
        "raw_responses": [],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def load_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Load and verify an immutable manifest and every hashed release input."""
    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise ManifestError(f"manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid manifest: {path}") from exc
    if payload.get("schema") != "frozen-forward-test/v1" or not payload.get("release_id"):
        raise ManifestError("invalid frozen manifest schema")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ManifestError("manifest has no immutable files")
    panel_path = payload.get("panel_path")
    if panel_path and panel_path not in files:
        raise ManifestError("manifest panel is not an immutable file")
    for raw_path, entry in files.items():
        item = Path(raw_path)
        if not item.is_file():
            raise ManifestError(f"manifest input is missing: {item}")
        actual = sha256_file(item)
        if actual != entry.get("sha256"):
            raise ManifestError(f"hash mismatch: {item}")
    return payload


def _read_panel(panel: pd.DataFrame | str | Path) -> pd.DataFrame:
    if isinstance(panel, (str, Path)):
        frame = pd.read_parquet(panel)
    else:
        frame = panel.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame = frame.sort_index()
    if frame.index.has_duplicates:
        raise ValueError("panel has duplicate sessions")
    missing = sorted(set(INSTRUMENT_MAP) - set(frame.columns))
    if missing:
        raise ValueError(f"panel is missing instruments: {missing}")
    if np.isinf(frame[list(INSTRUMENT_MAP)].to_numpy(dtype=float)).any():
        raise ValueError("panel contains infinite inputs")
    return frame


def _overlay_trace(returns: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Return the frozen V2 overlay trace and its net return.

    This mirrors ``book_oos_v4.apply_overlay`` so the audit implementation
    remains the single owner of the strategy rules.
    """
    rv = returns.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (0.10 / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    applied_gear = gear.shift(1).fillna(1.0)
    state = 1.0
    equity = hwm = 1.0
    engine_equity = engine_hwm = 1.0
    rows = []
    out = []
    for timestamp, value in returns.items():
        strategy_state = state
        gross = float(value)
        scaled = gross * float(applied_gear.loc[timestamp]) * strategy_state
        equity *= 1.0 + scaled
        hwm = max(hwm, equity)
        experienced_dd = equity / hwm - 1.0 if hwm else 0.0
        engine_equity *= 1.0 + gross
        prior_engine_hwm = engine_hwm
        engine_hwm = max(engine_hwm, engine_equity)
        if engine_equity >= prior_engine_hwm:
            state = 1.0
        elif experienced_dd <= -0.10:
            state = 0.0
        elif experienced_dd <= -0.06:
            state = 0.5
        rows.append({"overlay_state": strategy_state, "overlay_gear": float(applied_gear.loc[timestamp]),
                     "overlay_equity": equity, "overlay_hwm": hwm,
                     "overlay_drawdown": experienced_dd, "engine_equity": engine_equity,
                     "engine_hwm": engine_hwm})
        out.append(scaled)
    return pd.DataFrame(rows, index=returns.index), pd.Series(out, index=returns.index, dtype=float)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if value is None:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _cross_sectional_leg_positions(
    levels: Mapping[str, pd.Series], zdf: pd.DataFrame | None = None
) -> dict[str, pd.Series]:
    """Expose the corrected F2 legs for the audit ledger without changing it."""
    legs = ("crack_321", "crack_gas", "crack_ho")
    if zdf is None:
        zdf = pd.DataFrame({name: book.fb.seasonal_z(levels[name]) for name in legs})
    chosen = np.full(len(zdf), -1, dtype=int)
    values = zdf.to_numpy(dtype=float)
    for row in range(len(zdf)):
        if np.isfinite(values[row]).all():
            selected = int(np.argmin(values[row]))
            if values[row, selected] < book.fb.XS_MIN_Z:
                chosen[row] = selected
    output: dict[str, pd.Series] = {}
    for number, name in enumerate(legs):
        on = pd.Series(chosen == number, index=zdf.index)
        raw = pd.Series(1.0, index=zdf.index).where(on, 0.0)
        scaled = raw * book.fixed_vol_scale(levels[name], 0.50)
        output[name] = book.leg_risk(scaled, levels[name], trailing_stop=False)
    return output


def compute_frozen_state(panel: pd.DataFrame | str | Path = PANEL) -> pd.DataFrame:
    """Compute one causal state row per completed panel session."""
    frame = _read_panel(panel)
    levels = engine.build_levels(frame)
    positions, returns, turnover = book.build_v4(levels, cap3sig=None, vt_f2=0.50)
    valid_sessions = frame[list(INSTRUMENT_MAP)].notna().all(axis=1)
    for name in positions:
        positions[name] = positions[name].where(valid_sessions, 0.0)
    for name in turnover:
        turnover[name] = positions[name].diff().abs().fillna(0.0)
    net = book.apply_costs(positions, returns, turnover=turnover, trade_bps=5.0, roll_bps=20.0)
    net = net.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    weights = {name: 1.0 / 3.0 for name in FACTORS}
    net_book = book.book_returns(net, list(FACTORS), weights)
    gross_book = book.book_returns(pd.DataFrame(returns), list(FACTORS), weights).fillna(0.0)
    overlay, overlay_returns = _overlay_trace(net_book)
    # Per-leg F2 positions are retained for reconciliation and audit evidence.
    z_scores = {name: engine.seasonal_z(series) for name, series in levels.items()}
    f2_legs = _cross_sectional_leg_positions(
        levels, pd.DataFrame({name: z_scores[name] for name in ("crack_321", "crack_gas", "crack_ho")})
    )
    panel_hash = sha256_file(panel) if isinstance(panel, (str, Path)) else hashlib.sha256(
        pd.util.hash_pandas_object(frame[list(INSTRUMENT_MAP)], index=True).values.tobytes()
    ).hexdigest()
    rows: list[dict[str, Any]] = []
    for i, timestamp in enumerate(frame.index):
        scale = float(overlay.iloc[i]["overlay_state"] * overlay.iloc[i]["overlay_gear"])
        factor_raw = {name: float(positions[name].iloc[i]) for name in FACTORS}
        factor_scaled = {name: value * scale for name, value in factor_raw.items()}
        leg_positions = {name: factor_scaled[name] for name in ("crack_321", "bzwti")}
        leg_positions.update({name: float(series.iloc[i]) * scale for name, series in f2_legs.items()})
        raw_closes = {name: float(frame[name].iloc[i]) for name in INSTRUMENT_MAP}
        level_values = {name: float(series.iloc[i]) for name, series in levels.items()}
        z_values = {name: float(z_scores[name].iloc[i]) for name in levels}
        gross_lev = sum(weights[name] * abs(value) for name, value in factor_scaled.items())
        data_alerts = [] if bool(valid_sessions.iloc[i]) else ["missing input: flatten"]
        alerts = kill_alerts({"gross_leverage": gross_lev, "drawdown": overlay.iloc[i]["overlay_drawdown"],
                              "net_return": overlay_returns.iloc[i], "data_alerts": data_alerts})
        rows.append({
            "session": timestamp.strftime("%Y-%m-%d"),
            "event_sequence": i + 1,
            "input_hash": panel_hash,
            "raw_closes": raw_closes,
            "levels": level_values,
            "seasonal_z": z_values,
            "unscaled_signals": {name: float(np.sign(value)) for name, value in factor_raw.items()},
            "factor_weights": weights,
            "factor_positions": factor_scaled,
            "leg_positions": leg_positions,
            "gross_leverage": gross_lev,
            "net_leverage": sum(weights[name] * value for name, value in factor_scaled.items()),
            "overlay_state": float(overlay.iloc[i]["overlay_state"]),
            "overlay_gear": float(overlay.iloc[i]["overlay_gear"]),
            "overlay_equity": float(overlay.iloc[i]["overlay_equity"]),
            "overlay_drawdown": float(overlay.iloc[i]["overlay_drawdown"]),
            "engine_equity": float(overlay.iloc[i]["engine_equity"]),
            "engine_hwm": float(overlay.iloc[i]["engine_hwm"]),
            "gross_return": float(gross_book.iloc[i]),
            "net_return": float(overlay_returns.iloc[i]),
            "equity": float((1.0 + overlay_returns.iloc[: i + 1]).prod()),
            "drawdown": float((1.0 + overlay_returns.iloc[: i + 1]).prod() /
                               (1.0 + overlay_returns.iloc[: i + 1]).cummax().max() - 1.0),
            "turnover": float(sum(weights[name] * turnover[name].iloc[i] for name in FACTORS)),
            "data_alerts": data_alerts,
            "execution_alerts": [],
            "reconciliation_alerts": [],
            "alerts": alerts,
            "operator_acknowledged": False,
        })
    result = pd.DataFrame(rows, index=frame.index)
    return result


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise LedgerError("ledger contains invalid JSON") from exc
    return records


def append_daily_record(log_path: str | Path, record: Mapping[str, Any]) -> None:
    """Append one record, enforcing release identity and sequence ordering."""
    target = Path(log_path)
    item = _jsonable(dict(record))
    if not item.get("release_id"):
        raise LedgerError("record requires release_id")
    if "event_sequence" not in item or "session" not in item:
        raise LedgerError("record requires event_sequence and session")
    prior = _read_ledger(target)
    if prior:
        last = prior[-1]
        if item["release_id"] != last.get("release_id"):
            raise LedgerError("append-only ledger release mismatch")
        if int(item["event_sequence"]) != int(last["event_sequence"]) + 1:
            raise LedgerError("append-only ledger sequence mismatch")
        if str(item["session"]) <= str(last["session"]):
            raise LedgerError("append-only ledger session is not increasing")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_state_rows(log_path: str | Path, state: pd.DataFrame, release_id: str) -> int:
    prior = _read_ledger(Path(log_path))
    if prior and prior[-1].get("release_id") != release_id:
        raise LedgerError("append-only ledger release mismatch")
    last_session = str(prior[-1]["session"]) if prior else ""
    rows = [(index, row) for index, row in state.iterrows()
            if str(row.get("session", index.strftime("%Y-%m-%d"))) > last_session]
    count = 0
    for offset, (_, row) in enumerate(rows, start=len(prior) + 1):
        record = row.to_dict()
        record["release_id"] = release_id
        record["event_sequence"] = offset
        append_daily_record(log_path, record)
        count += 1
    return count


def reconcile(
    *,
    expected_positions: Mapping[str, float],
    actual_positions: Mapping[str, float],
    expected_cash: float,
    actual_cash: float,
    expected_equity: float,
    actual_equity: float,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Reconcile positions, cash, and equity independently of signal state."""
    symbols = sorted(set(expected_positions) | set(actual_positions))
    position_diffs = {symbol: float(actual_positions.get(symbol, 0.0) - expected_positions.get(symbol, 0.0))
                      for symbol in symbols}
    alerts = [f"position:{symbol}" for symbol, diff in position_diffs.items() if abs(diff) > tolerance]
    cash_diff = float(actual_cash - expected_cash)
    equity_diff = float(actual_equity - expected_equity)
    if abs(cash_diff) > tolerance:
        alerts.append("cash")
    if abs(equity_diff) > tolerance:
        alerts.append("equity")
    return {"ok": not alerts, "alerts": alerts, "position_diffs": position_diffs,
            "cash_difference": cash_diff, "equity_difference": equity_diff}


def reconcile_daily(**kwargs: Any) -> dict[str, Any]:
    return reconcile(**kwargs)


def kill_alerts(record: Mapping[str, Any], history: Iterable[Mapping[str, Any]] | None = None) -> list[str]:
    """Return hard-limit alerts for a daily record and its recent history."""
    alerts: list[str] = []
    def add(name: str) -> None:
        if name not in alerts:
            alerts.append(name)
    def number(name: str) -> float | None:
        value = record.get(name)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if np.isfinite(value) else None

    gross = number("gross_leverage")
    if gross is None:
        gross = number("gross_exposure")
    if gross is None or gross > 1.0 + 1e-9:
        add("gross_exposure")
    for name in ("factor_leverage", "leg_leverage"):
        value = number(name)
        if value is not None and value > 1.0 + 1e-9:
            add(name)
    dd = number("account_drawdown")
    if dd is None:
        dd = number("drawdown")
    if dd is not None and dd <= -0.15:
        add("account_drawdown")
    overlay_dd = number("overlay_drawdown")
    if overlay_dd is not None and overlay_dd <= -0.10:
        add("overlay_halt")
    daily = number("daily_net_return")
    if daily is None:
        daily = number("net_return")
    if daily is not None and daily <= -0.03:
        add("daily_loss")
    mark = number("mark_to_market_return")
    if mark is not None and mark <= -0.05:
        add("mark_to_market_loss")
    reconciliation = record.get("reconciliation")
    if isinstance(reconciliation, Mapping) and reconciliation.get("ok") is False:
        add("reconciliation")
    for field, name in (("data_alerts", "data"), ("execution_alerts", "execution"),
                        ("reconciliation_alerts", "reconciliation"), ("alerts", "nested_kill")):
        values = record.get(field, [])
        if isinstance(values, (list, tuple, set)) and values:
            add(name)
    if history is not None:
        recent = list(history)[-5:]
        if len(recent) >= 5:
            slippage = [float(item.get("slippage_bps_per_side", 0.0)) for item in recent]
            fills = [float(item.get("fill_rate", 1.0)) for item in recent]
            if all(np.isfinite(slippage)) and all(value > 25.0 for value in slippage):
                add("slippage_pause")
            if all(np.isfinite(fills)) and all(value < 0.80 for value in fills):
                add("fill_rate_pause")
    return alerts


def run_paper_test(manifest_path: str | Path, log_path: str | Path) -> int:
    manifest = load_manifest(manifest_path)
    panel_path = manifest.get("panel_path")
    if not panel_path or not Path(panel_path).is_file():
        panel_path = next(path for path in manifest["files"] if Path(path).suffix == ".parquet")
    state = compute_frozen_state(panel_path)
    return append_state_rows(log_path, state, manifest["release_id"])



def _refuse_contaminated_forward() -> None:
    """Refuse to run this superseded, contaminated forward test.

    Found by the 2026-09-22 audit:
      - the panel is yfinance raw front-month (NOT back-adjusted), so the
        roll gaps are booked as price moves; those sessions were 40.2% of
        the measured walk-forward P&L;
      - costs are hardcoded at 5 bps/side; the measured real round trip is
        16.2-24.0 bps per side.
    Use algoterminal-strategy-v2/research/forward_protocol_v3.md instead.
    Set I_ACKNOWLEDGE_CONTAMINATED_FORWARD=1 only to reproduce the old record.
    """
    import os
    if os.environ.get("I_ACKNOWLEDGE_CONTAMINATED_FORWARD") == "1":
        return
    raise SystemExit(
        "REFUSING TO RUN: this forward test is superseded and contaminated.\n"
        "  panel: panel_v2.parquet = yfinance raw front-month, NOT back-adjusted\n"
        "  costs: 5 bps/side hardcoded; measured real cost is 16.2-24.0 bps/side\n"
        "See algoterminal-strategy-v2/research/forward_protocol_v3.md.\n"
        "Set I_ACKNOWLEDGE_CONTAMINATED_FORWARD=1 to reproduce the old record."
    )


def main(argv: list[str] | None = None) -> int:
    _refuse_contaminated_forward()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    args = parser.parse_args(argv)
    print(f"appended {run_paper_test(args.manifest, args.log)} paper records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
