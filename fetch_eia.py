"""Fetch EIA weekly series through the repo provider into /tmp caches.

Requires EIA_API_KEY in the environment (export it in the shell that runs
pi). Uses the algoterminal-data repo's eia provider so caching works.

Usage:  PYTHONPATH=/home/sebas/algoterminal-data/src python3 fetch_eia.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "/home/sebas/algoterminal-data/src")

from algoterminal_data import get_data  # noqa: E402

SERIES = {
    "W_EPM0F_SAX_NUS_MBBL": "gasoline stocks",
    "W_EPD0_SAX_NUS_MBBL": "distillate stocks",
    "W_EPC0_SAX_NUS_MBBL": "crude stocks",
    "W_EPC0_SAX_YCX_MBBL": "cushing stocks",
    "NGW_EPG0_SWO_NUS_MMCF": "natgas working storage",
    "W_EPOOPT_Y_NUS_PCT": "refinery utilization",
}

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


if __name__ == "__main__":
    main()