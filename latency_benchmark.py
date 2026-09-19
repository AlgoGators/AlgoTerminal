"""Reproducible benchmark for the current daily signal and accounting path.

The signal workload calls the existing engine_v2 level, signal, sizing, and
risk functions. The measured seam is daily per-factor accounting: costs plus
the weighted book sum. The Rust kernel replaces only that seam and is checked
against the existing pandas result before timings are reported.

Examples:
    python latency_benchmark.py
    python latency_benchmark.py --panel panel_v2.parquet --repeats 3
    python latency_benchmark.py --rows 4096 --repeats 5 --json

Rust compilation time is reported separately and excluded from kernel timing.
The benchmark uses a batch FFI call, not a claim about one-call-per-day live
latency.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import io
import json
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import engine_v2


ROOT = Path(__file__).parent
RUST_SOURCE = ROOT / "rust_latency_kernel.rs"
DEFAULT_ROWS = 4096
DEFAULT_SEED = 17
DEFAULT_REPEATS = 5
FACTOR_NAMES = ("cross_sectional", "crack_321", "crack_ho", "ng", "bzwti")


@dataclass(frozen=True)
class Workload:
    """Prepared arrays at the Python/Rust accounting boundary."""

    positions: pd.DataFrame
    returns: pd.DataFrame
    turnover: pd.DataFrame
    weights: np.ndarray
    names: tuple[str, ...]
    trade_bps: float = engine_v2.TRADE_BPS
    roll_bps: float = engine_v2.ROLL_BPS


@dataclass(frozen=True)
class BenchmarkResult:
    workload: str
    rows: int
    factors: int
    accounting_days: int
    repeats: int
    signal_seconds: float
    rust_compile_seconds: float
    python_seconds: float
    rust_seconds: float
    speedup: float
    max_abs_error: float
    decision_difference_days: int
    decision_quality: str
    latency_decision_note: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def make_benchmark_panel(rows: int = DEFAULT_ROWS, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Return a fixed-shape, deterministic positive futures-like daily panel."""
    if rows < 1:
        raise ValueError("rows must be positive")
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2007-01-02", periods=rows)
    t = np.arange(rows, dtype=float)
    common = np.cumsum(rng.normal(0.0, 0.18, rows))
    cl = 72.0 + common + 2.0 * np.sin(t / 47.0)
    bz = cl + 1.8 + 0.35 * np.sin(t / 31.0) + rng.normal(0.0, 0.08, rows)
    rb = 2.05 + 0.015 * np.sin(t / 19.0) + rng.normal(0.0, 0.012, rows)
    ho = 2.25 + 0.020 * np.cos(t / 23.0) + rng.normal(0.0, 0.014, rows)
    ng = 3.10 + 0.30 * np.sin(t / 73.0) + np.cumsum(rng.normal(0.0, 0.012, rows))
    return pd.DataFrame({"CL": cl, "BZ": bz, "RB": rb, "HO": ho, "NG": ng}, index=index)


def prepare_workload(panel: pd.DataFrame, trade_bps: float = engine_v2.TRADE_BPS,
                     roll_bps: float = engine_v2.ROLL_BPS) -> Workload:
    """Run the existing signal path and freeze its arrays for accounting."""
    required = {"CL", "BZ", "RB", "HO", "NG"}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"panel missing columns: {sorted(missing)}")
    levels = engine_v2.build_levels(panel.sort_index())
    factors, returns, turnover = engine_v2.build_v2(levels)
    names = tuple(name for name in FACTOR_NAMES if name in returns)
    if len(names) != len(returns):
        raise ValueError(f"unexpected factors: {sorted(returns)}")
    positions_frame = pd.DataFrame({name: factors[name] for name in names})
    returns_frame = pd.DataFrame({name: returns[name] for name in names})
    turnover_frame = pd.DataFrame({name: turnover[name] for name in names})
    weights = np.full(len(names), 1.0 / len(names), dtype=np.float64)
    return Workload(positions_frame, returns_frame, turnover_frame, weights, names,
                    float(trade_bps), float(roll_bps))


def python_accounting(workload: Workload) -> pd.Series:
    """Run the unchanged pandas accounting path at the benchmark seam."""
    net = engine_v2.apply_costs(
        {name: workload.positions[name] for name in workload.names},
        {name: workload.returns[name] for name in workload.names},
        turnover={name: workload.turnover[name] for name in workload.names},
        trade_bps=workload.trade_bps,
        roll_bps=workload.roll_bps,
    )
    return engine_v2.book_returns(net, list(workload.names),
                                  dict(zip(workload.names, workload.weights)))


def _factor_major(frame: pd.DataFrame, *, fill_missing: bool = True) -> np.ndarray:
    """Convert a factor-column frame to factor-major C-order doubles."""
    if fill_missing:
        frame = frame.fillna(0.0)
    return np.ascontiguousarray(frame.to_numpy(dtype=np.float64).T)


def _compile_kernel() -> tuple[ctypes.CDLL, tempfile.TemporaryDirectory[str], float]:
    """Compile the source outside the repository and return its FFI handle."""
    temporary = tempfile.TemporaryDirectory(prefix="latency-kernel-")
    output = Path(temporary.name) / "liblatency_kernel.so"
    started = time.perf_counter()
    subprocess.run(
        ["rustc", str(RUST_SOURCE), "--crate-type", "cdylib", "-O", "-o", str(output)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    compiled_seconds = time.perf_counter() - started
    library = ctypes.CDLL(str(output))
    function = library.account_book
    double_pointer = ctypes.POINTER(ctypes.c_double)
    function.argtypes = [double_pointer, double_pointer, double_pointer, double_pointer,
                         ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double,
                         ctypes.c_double, double_pointer]
    function.restype = ctypes.c_int
    return library, temporary, compiled_seconds


def _call_rust(library: ctypes.CDLL, workload: Workload) -> np.ndarray:
    positions = _factor_major(workload.positions)
    returns = _factor_major(workload.returns, fill_missing=False)
    turnover = _factor_major(workload.turnover)
    weights = np.ascontiguousarray(workload.weights, dtype=np.float64)
    output = np.empty(len(workload.positions), dtype=np.float64)
    status = library.account_book(
        positions.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        returns.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        turnover.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        weights.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        len(output), len(workload.names), workload.trade_bps, workload.roll_bps,
        output.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if status != 0:
        raise RuntimeError(f"Rust accounting kernel returned status {status}")
    return output


def rust_accounting(workload: Workload) -> np.ndarray:
    """Compile, call, and clean up the tiny Rust accounting kernel."""
    library, temporary, _ = _compile_kernel()
    try:
        return _call_rust(library, workload)
    finally:
        temporary.cleanup()


def run_benchmark(panel: pd.DataFrame | None = None, *, rows: int = DEFAULT_ROWS,
                  seed: int = DEFAULT_SEED, repeats: int = DEFAULT_REPEATS) -> BenchmarkResult:
    """Benchmark signals once, then compare repeated Python and Rust accounting."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if panel is None:
        panel = make_benchmark_panel(rows, seed)
        workload_name = "synthetic deterministic daily panel"
    else:
        workload_name = "checked-in panel daily path"
        rows = len(panel)

    started = time.perf_counter()
    workload = prepare_workload(panel)
    signal_seconds = time.perf_counter() - started
    expected = python_accounting(workload)

    library, temporary, compile_seconds = _compile_kernel()
    try:
        rust_once = _call_rust(library, workload)
        python_started = time.perf_counter()
        for _ in range(repeats):
            python_accounting(workload)
        python_seconds = time.perf_counter() - python_started
        rust_started = time.perf_counter()
        for _ in range(repeats):
            rust_result = _call_rust(library, workload)
        rust_seconds = time.perf_counter() - rust_started
    finally:
        temporary.cleanup()

    max_error = float(np.max(np.abs(rust_once - expected.to_numpy())))
    difference_days = int(np.count_nonzero(~np.isclose(
        rust_once, expected.to_numpy(), rtol=0.0, atol=1e-12)))
    quality = "unchanged" if difference_days == 0 else "changed"
    speedup = python_seconds / rust_seconds if rust_seconds else float("inf")
    return BenchmarkResult(
        workload=workload_name,
        rows=rows,
        factors=len(workload.names),
        accounting_days=len(workload.positions),
        repeats=repeats,
        signal_seconds=signal_seconds,
        rust_compile_seconds=compile_seconds,
        python_seconds=python_seconds,
        rust_seconds=rust_seconds,
        speedup=speedup,
        max_abs_error=max_error,
        decision_difference_days=difference_days,
        decision_quality=quality,
        latency_decision_note=(
            "Lower latency cannot change daily decision quality here: both paths "
            "use the same frozen signals, inputs, costs, and accounting order."
        ),
    )


def _load_panel(path: str) -> pd.DataFrame:
    # Keep --json machine-readable because engine_v2.load_panel logs to stdout.
    with contextlib.redirect_stdout(io.StringIO()):
        return engine_v2.load_panel(Path(path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--panel", help="parquet panel; default is the deterministic fixture")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()
    result = run_benchmark(
        _load_panel(args.panel) if args.panel else None,
        rows=args.rows,
        seed=args.seed,
        repeats=args.repeats,
    )
    if args.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
        return
    print(f"Workload: {result.workload}, rows={result.rows}, factors={result.factors}, repeats={result.repeats}")
    print(f"Runtime: signal={result.signal_seconds:.6f}s, Python accounting={result.python_seconds:.6f}s, "
          f"Rust accounting={result.rust_seconds:.6f}s, compile={result.rust_compile_seconds:.6f}s, "
          f"speedup={result.speedup:.2f}x")
    print(f"Decision quality: {result.decision_quality}; differing daily results={result.decision_difference_days}; "
          f"max error={result.max_abs_error:.3e}")
    print(result.latency_decision_note)


if __name__ == "__main__":
    main()
