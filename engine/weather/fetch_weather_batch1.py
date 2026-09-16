"""Fetch NASA POWER daily T2M for Batch 1 (M2 cold-weather demand).

Saves engine/weather/raw_T2M_<LOC>.csv. Keyless public NASA data.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "/home/sebas/algoterminal-data")

from algoterminal_data._providers.nasa_power import NasaPowerProvider  # noqa: E402

OUT = Path("/home/sebas/algoterminal-strategy-v2/engine/weather")
OUT.mkdir(parents=True, exist_ok=True)

prov = NasaPowerProvider()
for loc in ("NYC", "HOUSTON"):
    df = prov.fetch(loc, start=date(2007, 1, 1), end=date(2026, 9, 15))
    if df is None or df.empty:
        print(f"{loc}: EMPTY")
        continue
    path = OUT / f"raw_T2M_{loc}.csv"
    df.to_csv(path)
    s = df.get("close", df.iloc[:, 0])
    print(f"{loc}: rows={len(df)} {df.index.min().date()}..{df.index.max().date()} "
          f"min={s.min():.2f} max={s.max():.2f} nan={int(s.isna().sum())}")
