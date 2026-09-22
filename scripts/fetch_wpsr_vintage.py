"""Fetch as-published (vintage) weekly product stocks from the EIA WPSR archive.

The H1 gate is a z-score on weekly U.S. product stocks. The frozen project
series (raw_WGTSTUS1.csv, raw_WDISTUS1.csv) are the CURRENT vintage: EIA
revises weekly stocks, so a historical date holds numbers that were not
public at the time. That is lookahead.

The EIA Weekly Petroleum Status Report archive publishes each release with
its own CSV tables, so the as-published values can be recovered. Each
release page is /archive/YYYY/YYYY_MM_DD/ and its table1.csv holds, at
release time, the current-week stocks.

Release date == availability date, so no separate publication lag is needed.

Output: engine/eia/raw_wpsr_vintage_gs.csv  (release_date,gas,dist)
        gas  = Total Motor Gasoline stocks, million barrels, as published
        dist = Distillate Fuel Oil stocks, million barrels, as published
"""
from __future__ import annotations

import csv
import io
import re
import time
from pathlib import Path

import requests

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
OUT = ROOT / "engine" / "eia" / "raw_wpsr_vintage_gs.csv"
INDEX = "https://www.eia.gov/petroleum/supply/weekly/archive/"
RELEASE = "https://www.eia.gov/petroleum/supply/weekly/archive/{y}/{y}_{m}_{d}/csv/table1.csv"
PAT = re.compile(r"archive/(\d{4})/(\d{4})_(\d{2})_(\d{2})/")


def release_dates() -> list[str]:
    html = requests.get(INDEX, timeout=60).text
    dates = sorted({f"{y}-{m}-{d}" for y, ymd, m, d in PAT.findall(html) if ymd == y})
    return dates


def extract(code: str) -> tuple[float, float] | None:
    r = requests.get(code, timeout=60)
    if r.status_code != 200:
        return None
    rows = list(csv.reader(io.StringIO(r.text)))
    gas = dist = None
    for row in rows:
        if len(row) < 2:
            continue
        label = row[0].strip().strip('"').lower()
        if gas is None and label in ("total motor gasoline", "motor gasoline"):
            try:
                gas = float(str(row[1]).replace(",", ""))
            except ValueError:
                pass
        if dist is None and label.startswith("distillate fuel oil"):
            try:
                dist = float(str(row[1]).replace(",", ""))
            except ValueError:
                pass
    if gas is None or dist is None:
        return None
    return gas, dist


def main() -> None:
    dates = release_dates()
    print(f"archive lists {len(dates)} releases: {dates[0]} .. {dates[-1]}")
    out = []
    misses = 0
    for i, d in enumerate(dates):
        y, m, dd = d.split("-")
        got = extract(RELEASE.format(y=y, m=m, d=dd))
        if got is None:
            misses += 1
        else:
            out.append((d, got[0], got[1]))
        if i % 100 == 0:
            print(f"  {i}/{len(dates)} ...")
        time.sleep(0.05)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["release_date", "gas", "dist"])
        w.writerows(out)
    print(f"wrote {OUT} rows={len(out)} misses={misses}")


if __name__ == "__main__":
    main()
