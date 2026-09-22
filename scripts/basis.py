"""Metric basis registry.

A metric can be arithmetically correct and still mislead, because it does not
say what it is a return ON. The audit found exactly this: the headline figures
were percentage changes of a spread with no notional, no margin, and no
capital base, so a number labelled "Sharpe" did not describe a portfolio.

Every reported series therefore carries an explicit basis. Any quoted series
without a basis entry fails the basis gate.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

CRACK_BASIS = (
    "return = change in the crack-spread level over a rolling mean of its "
    "absolute value. Per unit of 1000 bbl crack-spread notional. No margin, "
    "no leverage, no capital base. NOT a return on capital."
)
RAW_BASIS = "raw price levels. Units as published."

BASIS: dict[str, dict] = {
    "panel_v2": {"kind": "prices", "basis": RAW_BASIS + " yfinance front-month, not back-adjusted."},
    "panel_spot": {"kind": "prices", "basis": RAW_BASIS + " EIA daily spot, roll-free."},
    "walkforward_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
    "walkforward_causal_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
    "spot_fixed_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
    "spot_causal_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
    "wf_crush_futures_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
    "wf_crush_spot_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
    "walkforward_causal_loo_series.csv": {"kind": "strategy", "basis": CRACK_BASIS},
}

# series files that must be covered by a basis entry
AUTHORITATIVE = [k for k, v in BASIS.items() if v["kind"] == "strategy"]


def label(name: str) -> str:
    return BASIS.get(name, {}).get("basis", "BASIS NOT DECLARED")


def uncovered() -> list[str]:
    """Quoted series present in results/ with no basis entry."""
    out = []
    for p in sorted(RESULTS.glob("*_series.csv")):
        if p.name not in BASIS:
            out.append(p.name)
    return out


def header() -> str:
    return ("basis for the figures below: " + CRACK_BASIS)


if __name__ == "__main__":
    print(header())
    missing = uncovered()
    print("uncovered series:", missing if missing else "none")
    raise SystemExit(1 if missing else 0)
