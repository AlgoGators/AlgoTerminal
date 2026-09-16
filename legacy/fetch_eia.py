"""Fetch EIA weekly series through the repo provider into /tmp caches.

Requires EIA_API_KEY in the environment or the algoterminal-data project
secrets file (loaded by api_key()). Uses the repo's eia provider.

Series codes verified against the EIA v2 API (2026-09-10):
  WGTSTUS1                   U.S. total gasoline ending stocks (MBBL)
  WDISTUS1                   U.S. distillate fuel oil ending stocks (MBBL)
  WCESTUS1                   U.S. crude oil ending stocks excl SPR (MBBL)
  W_EPC0_SAX_YCUOK_MBBL      Cushing, OK crude oil ending stocks (MBBL)
  WPULEUS3                   U.S. refinery operable utilization rate (%)
  NW2_EPG0_SWO_R*_BCF        natgas working gas by storage region (BCF),
                             summed here into a U.S. total (NATOTAL)

Usage:  PYTHONPATH=/home/sebas/algoterminal-data/src python3 fetch_eia.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, "/home/sebas/algoterminal-data/src")

from algoterminal_data import get_data  # noqa: E402

SERIES = {
    "WGTSTUS1": "gasoline stocks",
    "WDISTUS1": "distillate stocks",
    "WCESTUS1": "crude stocks (excl SPR)",
    "W_EPC0_SAX_YCUOK_MBBL": "cushing stocks",
    "WPULEUS3": "refinery utilization",
}

NATGAS_REGIONS = [f"NW2_EPG0_SWO_R{r}_BCF" for r in (31, 32, 33, 34, 35, 48)]

START = date(2007, 1, 1)
END = date(2026, 9, 9)


def main() -> None:
    for sym, desc in SERIES.items():
        try:
            df = get_data(sym, source="eia", start=START, end=END)
        except RuntimeError as e:
            print(f"SKIP {sym} ({desc}): {e}")
            continue
        if df.empty:
            print(f"EMPTY {sym} ({desc})")
            continue
        df.to_csv(f"/tmp/eia_{sym}.csv")
        print(f"OK {sym} ({desc}): {len(df)} rows {df.index.min().date()} -> {df.index.max().date()}")

    # natgas U.S. total = sum of storage-region working gas codes
    frames = []
    for sym in NATGAS_REGIONS:
        try:
            df = get_data(sym, source="eia", start=START, end=END)
        except RuntimeError as e:
            print(f"SKIP natgas region {sym}: {e}")
            continue
        if not df.empty:
            frames.append(df["close"])
            print(f"OK natgas region {sym}: {len(df)} rows")
    if frames:
        tot = pd.concat(frames, axis=1).sum(axis=1).dropna()
        tot = tot[~tot.index.duplicated(keep="last")].sort_index()
        pd.DataFrame({"close": tot}).to_csv("/tmp/eia_NATOTAL.csv")
        print(f"OK NATOTAL: {len(tot)} rows {tot.index.min().date()} -> {tot.index.max().date()}")
    else:
        print("NATOTAL: no region data")


if __name__ == "__main__":
    main()