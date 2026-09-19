from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import forward_test as ft


REQUIRED = ["CL", "BZ", "RB", "HO", "NG"]


def panel(rows: int = 140) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="B")
    n = pd.Series(range(rows), index=index, dtype=float)
    return pd.DataFrame(
        {
            "CL": 50 + n * 0.01,
            "BZ": 52 + n * 0.01,
            "RB": 1.5 + n * 0.001,
            "HO": 1.6 + n * 0.001,
            "NG": 2.5 + n * 0.002,
        },
        index=index,
    )


def test_manifest_is_immutable_and_verifies_inputs(tmp_path: Path):
    panel_path = tmp_path / "panel.parquet"
    panel().to_parquet(panel_path)
    manifest_path = tmp_path / "manifest.json"

    created = ft.create_manifest(manifest_path, panel_path=panel_path, release_id="release-test")
    loaded = ft.load_manifest(manifest_path)
    assert loaded["release_id"] == "release-test"
    assert loaded["files"][str(panel_path.resolve())]["sha256"] == ft.sha256_file(panel_path)
    assert created == loaded

    panel_path.write_bytes(panel_path.read_bytes() + b"changed")
    with pytest.raises(ft.ManifestError, match="hash mismatch"):
        ft.load_manifest(manifest_path)


def test_frozen_state_is_causal_and_has_core3_overlay_fields():
    state = ft.compute_frozen_state(panel())
    assert list(state.index) == list(panel().index)
    assert {"crack_321", "cross_sectional", "bzwti"} <= set(state["factor_positions"].iloc[0])
    for name in ("overlay_state", "overlay_gear", "gross_leverage", "net_return", "equity", "drawdown", "alerts"):
        assert name in state.columns
    assert state["factor_weights"].iloc[0] == {"crack_321": 1 / 3, "cross_sectional": 1 / 3, "bzwti": 1 / 3}


def test_state_prefix_does_not_use_future_rows():
    prefix = ft.compute_frozen_state(panel(120))
    extended_panel = panel(150)
    extended_panel.iloc[125:, extended_panel.columns.get_loc("CL")] += 100.0
    extended = ft.compute_frozen_state(extended_panel)
    for column in ("overlay_state", "overlay_gear", "net_return", "factor_positions"):
        assert prefix[column].iloc[:100].tolist() == extended[column].iloc[:100].tolist()


def test_append_reconcile_and_kill_alerts(tmp_path: Path):
    log_path = tmp_path / "paper.jsonl"
    first = {"release_id": "r1", "event_sequence": 1, "session": "2024-01-02", "net_return": -0.01}
    second = {"release_id": "r1", "event_sequence": 2, "session": "2024-01-03", "net_return": -0.01}
    ft.append_daily_record(log_path, first)
    ft.append_daily_record(log_path, second)
    assert len(log_path.read_text().splitlines()) == 2
    with pytest.raises(ft.LedgerError, match="append-only"):
        ft.append_daily_record(log_path, second)

    reconciliation = ft.reconcile(
        expected_positions={"CL": 0.25},
        actual_positions={"CL": 0.25},
        expected_cash=100.0,
        actual_cash=100.0,
        expected_equity=100.0,
        actual_equity=100.0,
    )
    assert reconciliation["ok"] is True
    alerts = ft.kill_alerts(
        {
            "gross_leverage": 1.2,
            "drawdown": -0.16,
            "net_return": -0.04,
            "data_alerts": ["stale close"],
        }
    )
    assert {"gross_exposure", "account_drawdown", "daily_loss", "data"} <= set(alerts)


def test_manifest_payload_is_json_serializable(tmp_path: Path):
    path = tmp_path / "panel.parquet"
    panel().to_parquet(path)
    manifest = ft.create_manifest(tmp_path / "manifest.json", panel_path=path)
    json.dumps(manifest)
