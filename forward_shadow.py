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
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

import forward_test as frozen


ROOT = Path(__file__).resolve().parent
PANEL = ROOT / "panel_v2.parquet"
TICKERS = {"CL": "CL=F", "BZ": "BZ=F", "RB": "RB=F", "HO": "HO=F", "NG": "NG=F"}


class ShadowError(ValueError):
    """A shadow run cannot be completed safely."""


def _utc_date(value: str | pd.Timestamp | datetime | None) -> pd.Timestamp:
    stamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp.normalize()


def _response_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=True).encode("utf-8")).hexdigest()


def _close_series(downloaded: Any) -> pd.Series:
    if not isinstance(downloaded, pd.DataFrame) or downloaded.empty:
        return pd.Series(dtype=float)
    frame = downloaded
    if isinstance(frame.columns, pd.MultiIndex):
        if "Close" not in frame.columns.get_level_values(0):
            raise ShadowError("yfinance response has no Close field")
        frame = frame["Close"]
        if isinstance(frame, pd.DataFrame):
            frame = frame.iloc[:, 0]
    elif "Close" in frame.columns:
        frame = frame["Close"]
    elif len(frame.columns) == 1:
        frame = frame.iloc[:, 0]
    else:
        raise ShadowError("yfinance response has no Close field")
    series = pd.to_numeric(frame, errors="coerce")
    index = pd.to_datetime(series.index)
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    series.index = index.normalize()
    return series[~series.index.duplicated(keep="last")].dropna()


def fetch_current_closes(
    *,
    download: Callable[..., Any] | None = None,
    as_of: str | pd.Timestamp | datetime | None = None,
    lookback_days: int = 10,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Fetch each approved ticker and return its latest completed close.

    The returned frame can have different dates per ticker.
    ``run_shadow`` marks a leg stale when its date is not fresh for the run.
    """
    if download is None:
        import yfinance as yf

        download = yf.download
    cutoff = _utc_date(as_of)
    start = (cutoff - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = (cutoff + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    values: dict[str, pd.Series] = {}
    metadata: dict[str, dict[str, Any]] = {}
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for name, ticker in TICKERS.items():
        request = {"start": start, "end": end, "progress": False,
                   "auto_adjust": False, "multi_level_index": False}
        try:
            raw = download(ticker, **request)
            series = _close_series(raw)
            series = series[series.index <= cutoff]
            values[name] = series
            metadata[name] = {
                "source_id": "yfinance",
                "ticker": ticker,
                "request": request,
                "retrieved_utc": retrieved,
                "sha256": _response_hash(raw) if isinstance(raw, pd.DataFrame) else None,
                "latest_session": series.index[-1].strftime("%Y-%m-%d") if not series.empty else None,
                "rows": int(len(raw)) if isinstance(raw, pd.DataFrame) else 0,
            }
        except Exception as exc:  # A failed leg is data failure, not permission to trade.
            values[name] = pd.Series(dtype=float)
            metadata[name] = {
                "source_id": "yfinance", "ticker": ticker, "request": request,
                "retrieved_utc": retrieved, "sha256": None, "latest_session": None,
                "rows": 0, "error": f"{type(exc).__name__}: {exc}",
            }
    frame = pd.DataFrame(values).sort_index()
    return frame, metadata


def verify_release(manifest_path: str | Path) -> dict[str, Any]:
    """Verify every immutable release file and the frozen instrument map."""
    manifest = frozen.load_manifest(manifest_path)
    if manifest.get("instrument_map") != TICKERS:
        raise frozen.ManifestError("manifest instrument map differs from frozen release")
    panel_path = manifest.get("panel_path")
    if not panel_path or not Path(panel_path).is_file():
        raise frozen.ManifestError("manifest historical panel is missing")
    return manifest


def _normalise_current(current: pd.DataFrame) -> pd.DataFrame:
    frame = current.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    frame.index = frame.index.normalize()
    frame = frame.sort_index()
    if frame.index.has_duplicates:
        frame = frame[~frame.index.duplicated(keep="last")]
    for name in TICKERS:
        if name not in frame:
            frame[name] = np.nan
    return frame[list(TICKERS)].apply(pd.to_numeric, errors="coerce")


def _freshness(
    current: pd.DataFrame,
    metadata: Mapping[str, Mapping[str, Any]],
    *,
    as_of: str | pd.Timestamp | datetime | None,
    max_age_days: int,
) -> tuple[pd.Timestamp, list[str], dict[str, Any]]:
    if max_age_days < 0:
        raise ShadowError("max_age_days must be non-negative")
    run_date = _utc_date(as_of)
    if len(current):
        target = current.index.max()
        if as_of is None:
            run_date = target
    else:
        target = run_date
    alerts: list[str] = []
    checks: dict[str, Any] = {}
    for name, ticker in TICKERS.items():
        info = dict(metadata.get(name, {}))
        raw_date = info.get("latest_session")
        if raw_date is None and len(current) and current[name].notna().any():
            raw_date = current.index[current[name].notna()][-1].strftime("%Y-%m-%d")
        latest = pd.Timestamp(raw_date).normalize() if raw_date else None
        value = current[name].dropna().iloc[-1] if name in current and current[name].notna().any() else None
        age = (run_date - latest).days if latest is not None else None
        reasons: list[str] = []
        if value is None or not np.isfinite(float(value)):
            reasons.append("missing close")
        if latest is None:
            reasons.append("missing session")
        elif latest != target:
            reasons.append("stale close")
        elif age is not None and age > max_age_days:
            reasons.append("stale close")
        if info.get("error"):
            reasons.append("fetch error")
        if reasons:
            alerts.extend(f"{name}: {reason}" for reason in reasons)
        checks[name] = {"ticker": ticker, "latest_session": latest.strftime("%Y-%m-%d") if latest else None,
                        "age_days": age, "finite": value is not None and np.isfinite(float(value)) if value is not None else False,
                        "ok": not reasons}
    return target, alerts, checks


def _combined_panel(panel_path: str | Path, current: pd.DataFrame) -> pd.DataFrame:
    historical = pd.read_parquet(panel_path)
    historical = historical.copy()
    if not isinstance(historical.index, pd.DatetimeIndex):
        historical.index = pd.to_datetime(historical.index)
    if historical.index.tz is not None:
        historical.index = historical.index.tz_convert("UTC").tz_localize(None)
    historical.index = historical.index.normalize()
    historical = historical[list(TICKERS)]
    combined = pd.concat([historical, current], axis=0).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def run_shadow(
    manifest_path: str | Path,
    log_path: str | Path,
    *,
    current: pd.DataFrame | None = None,
    response_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    as_of: str | pd.Timestamp | datetime | None = None,
    max_age_days: int = 3,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Verify, compute one current state, and append one no-order record."""
    manifest = verify_release(manifest_path)
    if current is None:
        current, response_metadata = fetch_current_closes(as_of=as_of)
    current = _normalise_current(current)
    if as_of is not None:
        current = current.loc[current.index <= _utc_date(as_of)]
    metadata = response_metadata or {}
    target, data_alerts, freshness = _freshness(current, metadata, as_of=as_of, max_age_days=max_age_days)
    if target not in current.index:
        current.loc[target, :] = np.nan
        current = current.sort_index()
    panel_path = manifest["panel_path"]
    combined = _combined_panel(panel_path, current)
    state = frozen.compute_frozen_state(combined)
    # The shared harness stores a scalar max of daily returns in its account
    # drawdown field.
    # Recompute the cumulative path for the auditable shadow row.
    state = state.copy()
    equity_path = (1.0 + state["net_return"].astype(float).fillna(0.0)).cumprod()
    state["equity"] = equity_path
    state["drawdown"] = equity_path / equity_path.cummax() - 1.0
    row = state.loc[target]
    record = row.to_dict()
    record.update({
        "release_id": manifest["release_id"],
        "event_sequence": _next_sequence(Path(log_path), len(pd.read_parquet(panel_path))),
        "recorded_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_ids": {name: metadata.get(name, {}).get("source_id", "yfinance") for name in TICKERS},
        "raw_responses": {name: dict(metadata.get(name, {})) for name in TICKERS},
        "freshness": freshness,
        "data_alerts": data_alerts,
        "intended_orders": [],
        "shadow_positions": row.get("leg_positions", {}),
        "effective_positions": {},
        "flattened": bool(data_alerts),
        "flattened_positions": {name: 0.0 for name in row.get("leg_positions", {})},
        "order_status": "flattened_no_order" if data_alerts else "no_order_shadow",
        "flatten_reason": "; ".join(data_alerts) if data_alerts else None,
        "code_hashes": {name: entry.get("sha256") for name, entry in manifest["files"].items()},
        "historical_panel_hash": manifest["files"][str(Path(panel_path).resolve())]["sha256"],
        "data_hashes": {name: metadata.get(name, {}).get("sha256") for name in TICKERS},
        "dry_run": dry_run,
    })
    record["alerts"] = sorted(set(list(record.get("alerts", [])) + (["data"] if data_alerts else [])))
    if not dry_run:
        frozen.append_daily_record(log_path, record)
    return {"record": frozen._jsonable(record), "appended": not dry_run, "manifest": manifest}


def _next_sequence(log_path: Path, historical_rows: int) -> int:
    if not log_path.exists():
        return historical_rows + 1
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return historical_rows + 1
    return int(json.loads(lines[-1])["event_sequence"]) + 1



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
    frozen._refuse_contaminated_forward()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--as-of", type=str)
    parser.add_argument("--max-age-days", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_shadow(args.manifest, args.log, as_of=args.as_of,
                        max_age_days=args.max_age_days, dry_run=args.dry_run)
    status = result["record"]["order_status"]
    print(f"{status}: {result['record']['session']} ({'not appended' if args.dry_run else 'appended'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
