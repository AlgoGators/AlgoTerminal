"""Tests for the reproducible daily-path latency benchmark."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import latency_benchmark as bench


ROOT = Path(__file__).parent


def test_fixture_is_deterministic_and_has_the_daily_panel_shape():
    first = bench.make_benchmark_panel(64, seed=17)
    second = bench.make_benchmark_panel(64, seed=17)

    pd.testing.assert_frame_equal(first, second)
    assert list(first.columns) == ["CL", "BZ", "RB", "HO", "NG"]
    assert len(first) == 64
    assert first.index.is_monotonic_increasing
    assert first.notna().all().all()


def test_rust_accounting_matches_current_python_accounting():
    panel = bench.make_benchmark_panel(96, seed=17)
    workload = bench.prepare_workload(panel)
    workload.positions.iloc[0, 0] = 0.8
    workload.turnover.iloc[0, 0] = 0.4
    workload.returns.iloc[0, 0] = np.nan
    python_book = bench.python_accounting(workload)
    rust_book = bench.rust_accounting(workload)

    np.testing.assert_allclose(rust_book, python_book.to_numpy(), rtol=0.0, atol=1e-12)


def test_benchmark_reports_workload_runtime_and_decision_quality():
    result = bench.run_benchmark(rows=96, seed=17, repeats=2)

    assert result.rows == 96
    assert result.factors == 5
    assert result.accounting_days == 96
    assert result.python_seconds > 0.0
    assert result.rust_seconds > 0.0
    assert result.max_abs_error <= 1e-12
    assert result.decision_quality == "unchanged"
    assert result.decision_difference_days == 0


def test_cli_emits_reproducible_json_report():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "latency_benchmark.py"),
         "--rows", "32", "--seed", "17", "--repeats", "1", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    assert report["workload"] == "synthetic deterministic daily panel"
    assert report["rows"] == 32
    assert report["decision_quality"] == "unchanged"
