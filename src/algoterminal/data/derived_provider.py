"""DataProvider for synthetic price series computed from other instruments'
closes -- spreads, crack margins, basis levels -- anything that behaves like
a tradeable price series for backtest purposes but isn't itself a fetchable
ticker.

Each derived symbol is defined once in `FORMULAS`: the underlying market
legs it needs and a function combining their close series into one level.
Nothing here is cached under its own key -- every fetch recomputes from the
underlying legs, which are already cache-optimized by YFinanceProvider/
StooqProvider, so a derived series never goes stale relative to its inputs.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd

from algoterminal.data.composite_provider import CompositeProvider
from algoterminal.data.provider import AssetClass, DataProvider
from algoterminal.data.stooq_provider import StooqProvider
from algoterminal.data.yfinance_provider import YFinanceProvider

GALLONS = 42.0  # bbl -> gal, for the 42-gallon crack-spread convention


def _crack_321(legs: dict[str, pd.Series]) -> pd.Series:
    return (2 * legs["RB=F"] + legs["HO=F"]) / 3 * GALLONS - legs["CL=F"]


def _crack_gas(legs: dict[str, pd.Series]) -> pd.Series:
    return legs["RB=F"] * GALLONS - legs["CL=F"]


def _crack_ho(legs: dict[str, pd.Series]) -> pd.Series:
    return legs["HO=F"] * GALLONS - legs["CL=F"]


def _bzwti(legs: dict[str, pd.Series]) -> pd.Series:
    return legs["BZ=F"] - legs["CL=F"]


FORMULAS: dict[str, tuple[list[str], Callable[[dict[str, pd.Series]], pd.Series]]] = {
    "CRACK321": (["CL=F", "RB=F", "HO=F"], _crack_321),
    "CRACKGAS": (["CL=F", "RB=F"], _crack_gas),
    "CRACKHO": (["CL=F", "HO=F"], _crack_ho),
    "BZWTI": (["CL=F", "BZ=F"], _bzwti),
}

SYMBOLS: dict[str, str] = {
    "CRACK321": "WTI 3:2:1 crack spread level: (2*RBOB + Heating Oil) / 3 * 42 - WTI, $/bbl refining-margin proxy",
    "CRACKGAS": "WTI gasoline crack spread level: RBOB * 42 - WTI, $/bbl refining-margin proxy",
    "CRACKHO": "WTI heating-oil crack spread level: Heating Oil * 42 - WTI, $/bbl refining-margin proxy",
    "BZWTI": "Brent-WTI crude basis: Brent - WTI, $/bbl",
}


class DerivedProvider(DataProvider):
    """Synthetic price series computed from a formula over other legs' closes."""

    name = "derived"

    def __init__(self) -> None:
        self._legs = CompositeProvider([YFinanceProvider(), StooqProvider()])

    def fetch(
        self,
        symbol: str,
        asset_class: AssetClass = AssetClass.CUSTOM,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        key = symbol.upper()
        if key not in FORMULAS:
            return pd.DataFrame()

        leg_symbols, formula = FORMULAS[key]
        leg_data = self._legs.fetch_many(leg_symbols, AssetClass.FUTURE, start, end)

        closes: dict[str, pd.Series] = {}
        for leg in leg_symbols:
            df = leg_data.get(leg)
            if df is None or df.empty or "close" not in df:
                return pd.DataFrame()
            closes[leg] = df["close"]

        level = formula(closes).dropna()
        if level.empty:
            return pd.DataFrame()

        out = pd.DataFrame({"close": level})
        out.index.name = "date"
        return out
