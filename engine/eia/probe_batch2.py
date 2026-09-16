"""Batch 2 data feasibility probe.

Tests candidate sources for:
  item 4  electrical load (EIA weekly electricity, NYISO fallback)
  item 5  jet / naphtha product series (stooq/yfinance probes)
  item 6  weekly product supplied (EIA route candidates)
Prints only row counts and date ranges. Key is never printed.
"""
from __future__ import annotations

import sys
import requests
from datetime import date

sys.path.insert(0, "/home/sebas/algoterminal-data")
from algoterminal_data._config import api_key  # noqa: E402

BASE = "https://api.eia.gov/v2"


def eia_route(route: str, series: str, freq: str = "weekly") -> None:
    params = {
        "api_key": api_key("EIA_API_KEY"), "frequency": freq,
        "data[0]": "value", "facets[series][]": series,
        "length": "5000",
    }
    try:
        r = requests.get(f"{BASE}/{route}/data/", params=params, timeout=25)
        r.raise_for_status()
        rows = r.json().get("response", {}).get("data", [])
        if not rows:
            print(f"EIA {route} {series}: EMPTY")
            return
        periods = [x.get("period") for x in rows if x.get("period")]
        vals = [float(x["value"]) for x in rows if x.get("value") is not None]
        print(f"EIA {route} {series}: rows={len(rows)} {min(periods)}..{max(periods)} "
              f"min={min(vals):.1f} max={max(vals):.1f}")
    except Exception as exc:  # noqa: BLE001
        print(f"EIA {route} {series}: ERROR {type(exc).__name__}: {exc}")


def nyiso_probe() -> None:
    urls = [
        "https://mis.nyiso.com/public/csv/pal/20240101pal.csv",
        "https://mis.nyiso.com/public/load/load_2007.csv",
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=25)
            print(f"NYISO {u}: status {r.status_code} bytes {len(r.content)}")
        except Exception as exc:  # noqa: BLE001
            print(f"NYISO {u}: ERROR {type(exc).__name__}: {exc}")


def main() -> None:
    print("=== item 6: product supplied route candidates ===")
    for route in ("petroleum/pnp/wpsd", "petroleum/pnp/wiup", "petroleum/stoc/wstk"):
        eia_route(route, "WPRTOTUS1")
    print("\n=== item 4: EIA weekly electricity generation ===")
    for route, series in [("electricity/electric-power-operational-data", "ELEC.GEN.ALL-US99.A"),
                          ("electricity/electric-power-operational-data", "ELEC.GEN.ALL.US99.A")]:
        eia_route(route, series, freq="weekly")
    print("\n=== item 5: jet fuel stocks (stocks are the free proxy) ===")
    eia_route("petroleum/stoc/wstk", "WJSTUS1")   # jet fuel ending stocks
    eia_route("petroleum/stoc/wstk", "WPRSTUS1")  # propane? (residual)
    print("\n=== item 4: NYISO direct ===")
    nyiso_probe()
    print("\nProbe done.")


if __name__ == "__main__":
    main()
