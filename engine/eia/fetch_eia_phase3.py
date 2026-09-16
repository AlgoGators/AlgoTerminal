"""Fetch EIA weekly series for Phase 3 into the v2 frozen inputs.

Series are cached raw as engine/eia/raw_<code>.csv with only date/close.
The API key is read from the algoterminal-data project secrets and is
never printed. Data is public EIA data.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "/home/sebas/algoterminal-data")

from algoterminal_data._providers.eia import EiaProvider  # noqa: E402

OUT = Path("/home/sebas/algoterminal-strategy-v2/engine/eia")
OUT.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    # concept candidates (memory codes first, provider docstring codes second)
    ("gasoline stocks", ["WGTSTUS1", "W_EPM0F_SAX_NUS_MBBL"]),
    ("distillate stocks", ["WDISTUS1", "W_EPD0_SAX_NUS_MBBL"]),
    ("crude excl SPR", ["WCESTUS1", "W_EPC0_SAX_NUS_MBBL"]),
    ("Cushing stocks", ["W_EPC0_SAX_YCUOK_MBBL", "W_EPC0_SAX_YCX_MBBL"]),
    ("refinery utilization", ["WPULEUS3", "W_EPOOPT_Y_NUS_PCT"]),
    ("product supplied total", ["WPRTOTUS1"]),
    ("crude runs", ["WCRRIUS2", "W_EPC0_RIY_NUS_MBBL"]),
]

prov = EiaProvider()
for concept, codes in CANDIDATES:
    for code in codes:
        try:
            df = prov.fetch(code, start=date(2007, 1, 1), end=date(2026, 9, 15))
        except Exception as exc:  # noqa: BLE001
            print(f"{concept:<22} {code:<22} ERROR {type(exc).__name__}: {exc}")
            continue
        if df is None or df.empty:
            print(f"{concept:<22} {code:<22} EMPTY")
            continue
        path = OUT / f"raw_{code}.csv"
        df.to_csv(path)
        s = df["close"]
        print(f"{concept:<22} {code:<22} rows={len(df):>5} "
              f"{df.index.min().date()}..{df.index.max().date()} "
              f"min={s.min():.2f} max={s.max():.2f} nan={int(s.isna().sum())}")
