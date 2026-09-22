"""Build a roll-free panel for the same walk-forward machinery.

panel_v2.parquet uses yfinance continuous front-month futures
(CL=F/RB=F/HO=F), whose legs roll on different dates and inject
scheduled discontinuities into the crack series. This builds the
equivalent panel from EIA daily spot prices, which never roll:

  CL <- RWTC                       WTI Cushing          $/BBL
  RB <- EER_EPMRU_PF4_Y35NY_DPG    NY Harbor gasoline   $/GAL
  HO <- EER_EPD2DXL0_PF4_Y35NY_DPG NY Harbor ULSD       $/GAL
  BZ, NG <- carried from panel_v2 on matching dates (unused by the
            crack_321 walk-forward; kept so build_levels has all keys)

Output: engine/panel_spot.parquet  (new input; panel_v2 untouched).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
EIA = ROOT / "engine" / "eia"


def load(fname: str) -> pd.Series:
    d = pd.read_csv(EIA / fname, parse_dates=["period"]).set_index("period")
    s = d["value"].astype(float).sort_index()
    return s[~s.index.duplicated(keep="last")]


def main() -> None:
    cl = load("raw_spot_RWTC.csv")
    rb = load("raw_spot_gas_nyh.csv")
    ho = load("raw_spot_ulsd_nyh.csv")
    spot = pd.DataFrame({"CL": cl, "RB": rb, "HO": ho}).dropna()

    fut = pd.read_parquet(ROOT / "engine" / "panel_v2.parquet").sort_index()
    for col in ("BZ", "NG"):
        spot[col] = fut[col].reindex(spot.index).ffill()
    spot = spot[["CL", "BZ", "RB", "HO", "NG"]]

    out = ROOT / "engine" / "panel_spot.parquet"
    spot.to_parquet(out)
    print(f"wrote {out}  rows={len(spot)}  {spot.index.min().date()} .. {spot.index.max().date()}")
    print(f"cols={list(spot.columns)}  nan={spot.isna().sum().to_dict()}")


if __name__ == "__main__":
    main()
