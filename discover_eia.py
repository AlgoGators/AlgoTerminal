"""Discover the correct EIA v2 series facet codes for weekly energy series.

Queries the API metadata (recent data rows) for each dataset route and
prints the distinct series codes with their descriptive fields, so we can
pick the right facets for the storage-gate series.
"""

from __future__ import annotations

import sys
from collections import Counter

import requests

sys.path.insert(0, "/home/sebas/algoterminal-data/src")
from algoterminal_data._config import api_key  # noqa: E402

KEY = api_key("EIA_API_KEY")
BASE = "https://api.eia.gov/v2"

ROUTES = {
    "petroleum stoc/wstk": "petroleum/stoc/wstk",
    "natural-gas stor/wkly": "natural-gas/stor/wkly",
    "refinery refopec": "petroleum/refm/refopec",
}


def discover(route: str) -> None:
    params = {
        "api_key": KEY, "frequency": "weekly",
        "data[0]": "value",
        "sort[0][column]": "period", "sort[0][direction]": "desc",
        "length": "60",
    }
    try:
        r = requests.get(f"{BASE}/{route}/data/", params=params, timeout=30)
        r.raise_for_status()
        rows = r.json().get("response", {}).get("data", [])
    except Exception as e:
        print(f"{route}: ERROR {e}")
        return
    if not rows:
        print(f"{route}: no rows")
        return
    print(f"\n=== {route}: {len(rows)} recent rows, distinct series: ===")
    seen = {}
    for row in rows:
        s = row.get("series")
        if s not in seen:
            seen[s] = row
    for s, row in seen.items():
        desc = " | ".join(f"{k}={row.get(k)}" for k in
                          ("product-name", "process-name", "area-name", "units", "period"))
        print(f"  {s}")
        print(f"      {desc[:180]}")


for name, route in ROUTES.items():
    discover(route)