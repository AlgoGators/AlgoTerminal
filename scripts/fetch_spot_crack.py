"""Fetch roll-free NY Harbor spot crack legs from EIA v2 (daily spot).

Root cause of the v1/v2 artifact audit: the frozen panel is built from
yfinance continuous front-month futures (CL=F/RB=F/HO=F). Those legs roll
on different dates, so the crack series carries scheduled level
discontinuities (worst: the winter->summer gasoline spec switch, which
lifts RBOB on the first trading day of March every year).

Spot prices never roll. This script pulls the matching spot legs so the
same walk-forward machinery can be re-run on a series with no roll
artifact:
  RWTC                        WTI Cushing, OK          $/BBL
  EER_EPMRU_PF4_Y35NY_DPG     NY Harbor regular gas    $/GAL
  EER_EPD2DXL0_PF4_Y35NY_DPG  NY Harbor ULSD (No.2)    $/GAL

Output: engine/eia/raw_spot_<code>.csv (columns: period,value; EIA
native). Never edits a frozen input; adds new files only.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import requests

sys.path.insert(0, "/home/sebas/algoterminal-data/src")
from algoterminal_data._config import api_key  # noqa: E402

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
OUT = ROOT / "engine" / "eia"
URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
SERIES = {
    "RWTC": "raw_spot_RWTC.csv",
    "EER_EPMRU_PF4_Y35NY_DPG": "raw_spot_gas_nyh.csv",
    "EER_EPD2DXL0_PF4_Y35NY_DPG": "raw_spot_ulsd_nyh.csv",
}


def fetch_all(code: str) -> list[dict]:
    key = api_key("EIA_API_KEY")
    if not key:
        raise RuntimeError("EIA_API_KEY not set")
    rows: list[dict] = []
    offset = 0
    while True:
        r = requests.get(URL, params={
            "api_key": key, "frequency": "daily", "data[0]": "value",
            "facets[series][]": code, "start": "2000-01-01", "length": 5000,
            "offset": offset, "sort[0][column]": "period", "sort[0][direction]": "asc",
        }, timeout=60)
        r.raise_for_status()
        batch = r.json().get("response", {}).get("data", [])
        rows.extend(batch)
        if len(batch) < 5000:
            break
        offset += 5000
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for code, fname in SERIES.items():
        rows = fetch_all(code)
        rows = [x for x in rows if x.get("value") not in (None, "", ".")]
        path = OUT / fname
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["period", "value"])
            for x in rows:
                w.writerow([x["period"], x["value"]])
        print(f"{code:<28} -> {fname}  rows={len(rows)}  "
              f"{rows[0]['period'] if rows else '-'} .. {rows[-1]['period'] if rows else '-'}")


if __name__ == "__main__":
    main()
