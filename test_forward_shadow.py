from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import forward_shadow as fs
import forward_test as ft


TICKERS = {"CL": "CL=F", "BZ": "BZ=F", "RB": "RB=F", "HO": "HO=F", "NG": "NG=F"}


def panel(rows: int = 120) -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=rows, freq="B")
    n = pd.Series(range(rows), index=index, dtype=float)
    return pd.DataFrame(
        {"CL": 70 + n * 0.01, "BZ": 75 + n * 0.01, "RB": 2 + n * 0.001,
         "HO": 2.1 + n * 0.001, "NG": 3 + n * 0.002}, index=index
    )


def manifest(tmp_path: Path, panel_path: Path) -> Path:
    path = tmp_path / "release.json"
    ft.create_manifest(path, panel_path=panel_path, release_id="release-shadow",
                       source_paths=[fs.__file__])
    return path


def test_fetch_current_closes_uses_latest_close_and_records_hashes(monkeypatch):
    calls = []

    def download(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return pd.DataFrame({"Close": [10.0, 11.0]},
                            index=pd.to_datetime(["2025-01-02", "2025-01-03"]))

    frame, responses = fs.fetch_current_closes(download=download, as_of="2025-01-04")
    assert {c[0] for c in calls} == set(TICKERS.values())
    assert frame.loc[pd.Timestamp("2025-01-03"), "CL"] == 11.0
    assert all(item["sha256"] for item in responses.values())
    assert all(item["ticker"] in TICKERS.values() for item in responses.values())


def test_stale_or_missing_data_flattens_and_dry_run_does_not_append(tmp_path: Path):
    panel_path = tmp_path / "panel.parquet"
    panel().to_parquet(panel_path)
    release = manifest(tmp_path, panel_path)
    log = tmp_path / "shadow.jsonl"
    current = pd.DataFrame({"CL": [71.0], "BZ": [76.0], "RB": [2.1], "HO": [2.2], "NG": [3.1]},
                           index=pd.to_datetime(["2025-01-01"]))
    result = fs.run_shadow(release, log, current=current, response_metadata={}, dry_run=True,
                           as_of="2025-01-06")
    assert result["record"]["order_status"] == "flattened_no_order"
    assert result["record"]["effective_positions"] == {}
    assert result["record"]["flattened"] is True
    assert all(value == 0.0 for value in result["record"]["flattened_positions"].values())
    assert any("stale" in alert or "missing" in alert for alert in result["record"]["data_alerts"])
    assert not log.exists()


def test_valid_current_data_appends_auditable_no_order(tmp_path: Path):
    panel_path = tmp_path / "panel.parquet"
    panel().to_parquet(panel_path)
    release = manifest(tmp_path, panel_path)
    log = tmp_path / "shadow.jsonl"
    date = panel().index[-1] + pd.Timedelta(days=1)
    current = pd.DataFrame({key: [float(i + 1)] for i, key in enumerate(TICKERS)}, index=[date])
    result = fs.run_shadow(release, log, current=current,
                           response_metadata={key: {"sha256": "test"} for key in TICKERS})
    record = result["record"]
    assert record["order_status"] == "no_order_shadow"
    assert record["intended_orders"] == []
    assert record["release_id"] == "release-shadow"
    assert record["input_hash"]
    assert record["drawdown"] <= 0.0
    assert record["code_hashes"]
    assert record["data_hashes"]["CL"] == "test"
    assert json.loads(log.read_text())["event_sequence"] == len(panel()) + 1


def test_future_rows_are_not_used(tmp_path: Path):
    panel_path = tmp_path / "panel.parquet"
    panel().to_parquet(panel_path)
    release = manifest(tmp_path, panel_path)
    future = pd.DataFrame({key: [1.0] for key in TICKERS}, index=pd.to_datetime(["2030-01-01"]))
    result = fs.run_shadow(release, tmp_path / "shadow.jsonl", current=future, as_of="2029-01-01",
                           dry_run=True)
    assert result["record"]["session"] == "2029-01-01"
    assert result["record"]["flattened"] is True


def test_manifest_tamper_is_rejected(tmp_path: Path):
    panel_path = tmp_path / "panel.parquet"
    panel().to_parquet(panel_path)
    release = manifest(tmp_path, panel_path)
    panel_path.write_bytes(panel_path.read_bytes() + b"tamper")
    with pytest.raises(ft.ManifestError, match="hash mismatch"):
        fs.verify_release(release)
