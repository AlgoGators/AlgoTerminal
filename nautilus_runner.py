"""Tiny, deterministic NautilusTrader futures contract spike.

The module does not add NautilusTrader as a project dependency.
Run it in a temporary virtual environment with a pinned NautilusTrader wheel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from contract_adapter import Contract, ContractAdapter, MarketBar, Roll, Target


UTC = timezone.utc


@dataclass(frozen=True)
class FixtureContract:
    symbol: str
    root: str
    expiry: date
    multiplier: int
    tick_size: float = 0.01


@dataclass(frozen=True)
class Fixture:
    contracts: tuple[FixtureContract, ...]
    bars: tuple[MarketBar, ...]
    transitions: tuple[tuple[datetime, str, str, str], ...]


@dataclass(frozen=True)
class NautilusResult:
    status: str
    fill_probability: float
    slippage_probability: float
    contracts: tuple[str, ...] = ()
    fills: int = 0
    gross_pnl: float | None = None
    error: str | None = None


def _utc(day: int) -> datetime:
    return datetime(2025, 1, day, tzinfo=UTC)


def build_fixture() -> Fixture:
    """Return two dated contracts and an explicit old-to-new transition."""
    old = FixtureContract("CLF25", "CL", date(2025, 1, 20), 1_000)
    new = FixtureContract("CLG25", "CL", date(2025, 2, 20), 1_000)
    bars = (
        MarketBar(_utc(9), old.symbol, 70.0, 70.0),
        MarketBar(_utc(10), old.symbol, 70.0, 71.0),
        MarketBar(_utc(10), new.symbol, 72.0, 72.0),
        MarketBar(_utc(13), new.symbol, 72.0, 73.0),
    )
    transitions = ((_utc(10), old.symbol, new.symbol, "scheduled"),)
    return Fixture((old, new), bars, transitions)


def compare_with_contract_adapter(fixture: Fixture | None = None) -> dict[str, float | int]:
    """Run the neutral reference ledger against the exact fixture."""
    fixture = fixture or build_fixture()
    contracts = {
        item.symbol: Contract(
            item.symbol,
            root=item.root,
            expiry=item.expiry,
            multiplier=item.multiplier,
            tick_size=item.tick_size,
        )
        for item in fixture.contracts
    }
    first_bar = fixture.bars[0].timestamp
    transition_time, old_symbol, new_symbol, reason = fixture.transitions[0]
    result = ContractAdapter(contracts).run(
        fixture.bars,
        [Target(first_bar, old_symbol, 1)],
        rolls=[Roll(transition_time, "CL", old_symbol, new_symbol, reason=reason)],
    )
    return {
        "gross_pnl": result.gross_pnl,
        "roll_cost": result.roll_cost,
        "net_pnl": result.net_pnl,
        "fills": len(result.fills),
        "rolls": len(result.rolls),
    }


def _timestamp(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def _run_nautilus(fixture: Fixture, fill_probability: float, slippage_probability: float) -> int:
    """Run the fixture through NautilusTrader's low-level backtest engine."""
    from nautilus_trader.backtest.config import BacktestEngineConfig
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.backtest.models import FillModel
    from nautilus_trader.model.data import Bar, BarSpecification, BarType
    from nautilus_trader.model.enums import (
        AccountType,
        AggregationSource,
        AssetClass,
        BarAggregation,
        OmsType,
        OrderSide,
        PriceType,
        TimeInForce,
    )
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import FuturesContract
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity
    from nautilus_trader.trading.config import StrategyConfig
    from nautilus_trader.trading.strategy import Strategy

    venue = Venue("SIM")
    currency = Currency.from_str("USD")
    instruments: dict[str, Any] = {}
    bar_types: dict[str, Any] = {}
    for item in fixture.contracts:
        instrument_id = InstrumentId(Symbol(item.symbol), venue)
        instruments[item.symbol] = instrument_id
        bar_types[item.symbol] = BarType(
            instrument_id,
            BarSpecification(1, BarAggregation.DAY, PriceType.LAST),
            AggregationSource.EXTERNAL,
        )

    class FixtureStrategy(Strategy):
        def __init__(self) -> None:
            super().__init__(StrategyConfig())
            self.fills: list[Any] = []
            self.sent: set[tuple[str, str]] = set()

        def on_start(self) -> None:
            for bar_type in bar_types.values():
                self.subscribe_bars(bar_type)

        def _send(self, symbol: str, side: Any, key: str) -> None:
            marker = (symbol, key)
            if marker in self.sent:
                return
            self.sent.add(marker)
            order = self.order_factory.market(
                instrument_id=instruments[symbol],
                order_side=side,
                quantity=Quantity.from_int(1),
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)

        def on_bar(self, bar: Any) -> None:
            symbol = bar.bar_type.instrument_id.symbol.value
            day = datetime.fromtimestamp(bar.ts_event / 1_000_000_000, UTC).day
            if symbol == fixture.contracts[0].symbol and day == 9:
                self._send(symbol, OrderSide.BUY, "open")
            elif symbol == fixture.contracts[0].symbol and day == 10:
                self._send(symbol, OrderSide.SELL, "roll-close")
            elif symbol == fixture.contracts[1].symbol and day == 10:
                self._send(symbol, OrderSide.BUY, "roll-open")

        def on_order_filled(self, event: Any) -> None:
            self.fills.append(event)

    engine = BacktestEngine(
        BacktestEngineConfig(trader_id="NAUTILUS-001", run_analysis=False),
    )
    engine.add_venue(
        venue,
        OmsType.NETTING,
        AccountType.MARGIN,
        [Money(100_000, currency)],
        base_currency=currency,
        fill_model=FillModel(
            prob_fill_on_limit=fill_probability,
            prob_slippage=slippage_probability,
            random_seed=7,
        ),
        bar_execution=True,
    )
    for item in fixture.contracts:
        engine.add_instrument(
            FuturesContract(
                instruments[item.symbol],
                Symbol(item.symbol),
                AssetClass.COMMODITY,
                currency,
                2,
                Price.from_str("0.01"),
                Quantity.from_int(item.multiplier),
                Quantity.from_int(1),
                item.root,
                _timestamp(datetime(2025, 1, 1, tzinfo=UTC)),
                _timestamp(datetime.combine(item.expiry, datetime.min.time(), tzinfo=UTC)),
                _timestamp(datetime(2025, 1, 1, tzinfo=UTC)),
                _timestamp(datetime(2025, 1, 1, tzinfo=UTC)),
                exchange="SIM",
            ),
        )
    data = []
    for market_bar in fixture.bars:
        data.append(
            Bar(
                bar_types[market_bar.symbol],
                Price.from_str(f"{market_bar.open:.2f}"),
                Price.from_str(f"{max(market_bar.open, market_bar.close):.2f}"),
                Price.from_str(f"{min(market_bar.open, market_bar.close):.2f}"),
                Price.from_str(f"{market_bar.close:.2f}"),
                Quantity.from_int(1),
                _timestamp(market_bar.timestamp),
                _timestamp(market_bar.timestamp),
            ),
        )
    engine.add_data(data)
    strategy = FixtureStrategy()
    engine.add_strategy(strategy)
    engine.run()
    fills = len(strategy.fills)
    engine.dispose()
    return fills


def run_fixture(
    *, fill_probability: float = 1.0, slippage_probability: float = 0.0
) -> NautilusResult:
    """Attempt the pinned-engine run and preserve an unavailable-engine result."""
    for name, value in (
        ("fill_probability", fill_probability),
        ("slippage_probability", slippage_probability),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
    fixture = build_fixture()
    try:
        fills = _run_nautilus(fixture, fill_probability, slippage_probability)
    except ModuleNotFoundError as exc:
        return NautilusResult(
            "unavailable", fill_probability, slippage_probability,
            tuple(item.symbol for item in fixture.contracts), error=str(exc),
        )
    except Exception as exc:  # Keep the report reproducible when APIs drift.
        return NautilusResult(
            "failed", fill_probability, slippage_probability,
            tuple(item.symbol for item in fixture.contracts), error=f"{type(exc).__name__}: {exc}",
        )
    return NautilusResult(
        "valid", fill_probability, slippage_probability,
        tuple(item.symbol for item in fixture.contracts), fills=fills,
    )


if __name__ == "__main__":
    print(run_fixture())
    print(compare_with_contract_adapter())
