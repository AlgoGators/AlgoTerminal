"""Fetch NYMEX futures settlement prices per contract number (EIA v2).

The frozen panel uses yfinance continuous front-month futures, which
roll each leg on its own date and inject phantom level jumps into the
crack spread. EIA's `petroleum/pri/fut` route gives contract 1, 2, 3, 4
separately, which lets us build a true same-delivery-month crack spread
with one common roll date, and measure the real roll carry instead of
assuming 20 bps/yr.

Series (daily, $/BBL for WTI, $/GAL for products):
  WTI  RCLC1..RCLC4
  RBOB EER_EPMRR_PE{k}_Y35NY_DPG
  HO   EER_EPD2F_PE{k}_Y35NY_DPG

Coverage ends 2024-04-05 (EIA retired the daily futures route).

Output: engine/eia/raw_fut_<leg>_c<k>.csv (columns: period,value).
New files only; no frozen input is touched.
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
URL = "https://api.eia.gov/v2/petroleum/pri/fut/data/"

CODES = {}
for k in (1, 2, 3, 4):
    CODES[f"raw_fut_wti_c{k}.csv"] = f"RCLC{k}"
    CODES[f"raw_fut_rbob_c{k}.csv"] = f"EER_EPMRR_PE{k}_Y35NY_DPG"
    CODES[f"raw_fut_ho_c{k}.csv"] = f"EER_EPD2F_PE{k}_Y35NY_DPG"


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
        batch = [x for x in r.json().get("response", {}).get("data", [])
                 if x.get("value") not in (None, "", ".")]
        rows.extend(batch)
        if len(batch) < 5000:
            break
        offset += 5000
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for fname, code in CODES.items():
        rows = fetch_all(code)
        if not rows:
            print(f"{code:<28} -> {fname}  NO DATA")
            continue
        with (OUT / fname).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["period", "value"])
            for x in rows:
                w.writerow([x["period"], x["value"]])
        print(f"{code:<28} -> {fname}  n={len(rows)}  {rows[0]['period']} .. {rows[-1]['period']}")


if __name__ == "__main__":
    main()
