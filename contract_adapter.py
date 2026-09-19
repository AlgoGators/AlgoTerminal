"""Small contract-aware accounting seam for bar replay or a broker adapter.

The adapter keeps contract identity and raw prices at the accounting boundary.
Targets are decisions at a bar timestamp and fill on the next available bar.
Roll instructions are explicit: they close the old contract at its bar close
and open the new contract at its bar open.  The ledger separates raw PnL,
commission, configurable slippage, and roll cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Mapping


@dataclass(frozen=True)
class Contract:
    """Immutable metadata needed to value one futures contract."""

    symbol: str
    root: str
    expiry: date
    multiplier: float
    tick_size: float = 0.01
    currency: str = "USD"
    initial_margin: float | None = None


@dataclass(frozen=True)
class MarketBar:
    """One raw OHLC bar and optional executable bid/ask quote."""

    timestamp: datetime
    symbol: str
    open: float
    close: float
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class Target:
    """Absolute target quantity decided at ``timestamp``."""

    timestamp: datetime
    symbol: str
    quantity: float


@dataclass(frozen=True)
class Roll:
    """Instruction to replace one root's old contract with a new contract."""

    timestamp: datetime
    root: str
    old_symbol: str
    new_symbol: str
    quantity: float | None = None
    reason: str = "scheduled"


@dataclass(frozen=True)
class Fill:
    timestamp: datetime
    symbol: str
    quantity: float
    price: float
    reference_price: float
    fee_cost: float
    slippage_cost: float
    cash_flow: float
    kind: str = "target"


@dataclass(frozen=True)
class RollRecord:
    timestamp: datetime
    root: str
    old_symbol: str
    new_symbol: str
    quantity: float
    old_close_cash_flow: float
    new_open_cash_flow: float
    cash_flow: float
    cost: float
    reason: str


@dataclass(frozen=True)
class AccountingRow:
    timestamp: datetime
    gross_pnl: float
    fee_cost: float
    slippage_cost: float
    roll_cost: float
    net_pnl: float


@dataclass(frozen=True)
class AccountingResult:
    rows: tuple[AccountingRow, ...]
    fills: tuple[Fill, ...]
    rolls: tuple[RollRecord, ...]

    @property
    def gross_pnl(self) -> float:
        return sum(row.gross_pnl for row in self.rows)

    @property
    def fee_cost(self) -> float:
        return sum(row.fee_cost for row in self.rows)

    @property
    def slippage_cost(self) -> float:
        return sum(row.slippage_cost for row in self.rows)

    @property
    def roll_cost(self) -> float:
        return sum(row.roll_cost for row in self.rows)

    @property
    def net_pnl(self) -> float:
        return sum(row.net_pnl for row in self.rows)


# Neutral aliases make the seam easy to map to another engine's vocabulary.
ContractSpec = Contract
Bar = MarketBar
Decision = Target
RollInstruction = Roll


class ContractAdapter:
    """Replay target decisions against raw contract bars.

    This is deliberately an accounting seam, not a strategy or exchange
    simulator.  A later LEAN or Nautilus adapter can produce the same bars,
    targets, and roll instructions and consume the same fill ledger.
    """

    def __init__(
        self,
        contracts: Mapping[str, Contract],
        *,
        commission_per_contract: float = 0.0,
        slippage_ticks: float = 0.0,
        missing_data: str = "raise",
    ) -> None:
        if commission_per_contract < 0 or slippage_ticks < 0:
            raise ValueError("cost parameters must be non-negative")
        if missing_data not in {"raise", "skip"}:
            raise ValueError("missing_data must be 'raise' or 'skip'")
        self.contracts = dict(contracts)
        self.commission_per_contract = float(commission_per_contract)
        self.slippage_ticks = float(slippage_ticks)
        self.missing_data = missing_data

    def run(
        self,
        bars: Iterable[MarketBar],
        targets: Iterable[Target] = (),
        *,
        rolls: Iterable[Roll] = (),
    ) -> AccountingResult:
        """Return an auditable ledger for the supplied deterministic fixture.

        A target at ``t`` is filled on the first bar strictly after ``t``.
        A roll at ``t`` is executed on the first bar at or after ``t``.  Roll
        cash flows are notional futures cash flows for auditability; raw PnL
        remains mark-to-market price change times quantity times multiplier.
        """
        ordered_bars = sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))
        target_events = list(targets)
        roll_events = list(rolls)
        if not ordered_bars:
            return AccountingResult((), (), ())
        self._validate_symbols(ordered_bars, target_events, roll_events)
        by_time: dict[datetime, dict[str, MarketBar]] = {}
        for bar in ordered_bars:
            by_time.setdefault(bar.timestamp, {})[bar.symbol] = bar
        times = sorted(by_time)

        target_at: dict[datetime, list[Target]] = {}
        for target in target_events:
            fill_time = next((t for t in times if t > target.timestamp), None)
            if fill_time is not None:
                target_at.setdefault(fill_time, []).append(target)

        roll_at: dict[datetime, list[Roll]] = {}
        for roll in roll_events:
            fill_time = next((t for t in times if t >= roll.timestamp), None)
            if fill_time is not None:
                roll_at.setdefault(fill_time, []).append(roll)

        positions: dict[str, float] = {}
        marks: dict[str, float] = {}
        fills: list[Fill] = []
        roll_records: list[RollRecord] = []
        rows: list[AccountingRow] = []

        for timestamp in times:
            bars_now = by_time[timestamp]
            gross = fee = slippage = roll_cost = 0.0
            old_symbols = {roll.old_symbol for roll in roll_at.get(timestamp, ())}

            # Mark the overnight/open move before any next-bar target fills.
            for symbol, quantity in list(positions.items()):
                if not quantity or symbol in old_symbols:
                    continue
                bar = bars_now.get(symbol)
                if bar is None:
                    self._missing(symbol, timestamp)
                    continue
                gross += self._pnl(quantity, marks[symbol], bar.open, symbol)
                marks[symbol] = bar.open

            # Strategy targets execute at the current bar open.
            for target in target_at.get(timestamp, ()):
                bar = self._require_bar(bars_now, target.symbol, timestamp)
                current = positions.get(target.symbol, 0.0)
                order_quantity = target.quantity - current
                if order_quantity:
                    fill = self._make_fill(bar, order_quantity, bar.open, "target")
                    fills.append(fill)
                    fee += fill.fee_cost
                    slippage += fill.slippage_cost
                    positions[target.symbol] = target.quantity
                    marks[target.symbol] = bar.open

            # A roll is an old close at the raw close and a new open at the raw
            # open.  Both legs are retained in the ledger as individual fills.
            for instruction in roll_at.get(timestamp, ()):
                old_bar = self._require_bar(bars_now, instruction.old_symbol, timestamp)
                new_bar = self._require_bar(bars_now, instruction.new_symbol, timestamp)
                old_quantity = positions.get(instruction.old_symbol, 0.0)
                quantity = old_quantity if instruction.quantity is None else instruction.quantity
                if old_quantity and instruction.quantity is not None and old_quantity != instruction.quantity:
                    raise ValueError("roll quantity must match the old position")
                if old_quantity:
                    gross += self._pnl(
                        old_quantity,
                        marks[instruction.old_symbol],
                        old_bar.close,
                        instruction.old_symbol,
                    )
                if quantity:
                    old_fill = self._make_fill(
                        old_bar, -quantity, old_bar.close, "roll-old"
                    )
                    new_fill = self._make_fill(
                        new_bar, quantity, new_bar.open, "roll-new"
                    )
                    fills.extend((old_fill, new_fill))
                    fee += old_fill.fee_cost + new_fill.fee_cost
                    slippage += old_fill.slippage_cost + new_fill.slippage_cost
                    old_cash = old_fill.cash_flow
                    new_cash = new_fill.cash_flow
                    cash_flow = old_cash + new_cash
                    # Keep spread/slippage separate from the raw roll
                    # economics represented by the two reference prices.
                    old_raw_cash = (
                        quantity
                        * old_fill.reference_price
                        * self.contracts[instruction.old_symbol].multiplier
                    )
                    new_raw_cash = (
                        -quantity
                        * new_fill.reference_price
                        * self.contracts[instruction.new_symbol].multiplier
                    )
                    cost = -(old_raw_cash + new_raw_cash)
                    roll_records.append(
                        RollRecord(
                            timestamp,
                            instruction.root,
                            instruction.old_symbol,
                            instruction.new_symbol,
                            quantity,
                            old_cash,
                            new_cash,
                            cash_flow,
                            cost,
                            instruction.reason,
                        )
                    )
                    roll_cost += cost
                    positions.pop(instruction.old_symbol, None)
                    marks.pop(instruction.old_symbol, None)
                    positions[instruction.new_symbol] = quantity
                    marks[instruction.new_symbol] = new_bar.open

            # Mark the intrabar move after fills.  The baseline is the raw
            # reference price, so configured slippage is charged once below.
            for symbol, quantity in list(positions.items()):
                if not quantity:
                    continue
                bar = bars_now.get(symbol)
                if bar is None:
                    self._missing(symbol, timestamp)
                    continue
                gross += self._pnl(quantity, marks[symbol], bar.close, symbol)
                marks[symbol] = bar.close

            rows.append(
                AccountingRow(
                    timestamp,
                    gross,
                    fee,
                    slippage,
                    roll_cost,
                    gross - fee - slippage - roll_cost,
                )
            )

        return AccountingResult(tuple(rows), tuple(fills), tuple(roll_records))

    def _validate_symbols(
        self,
        bars: Iterable[MarketBar],
        targets: Iterable[Target],
        rolls: Iterable[Roll],
    ) -> None:
        symbols = [bar.symbol for bar in bars]
        symbols.extend(target.symbol for target in targets)
        for roll in rolls:
            symbols.extend((roll.old_symbol, roll.new_symbol))
        for symbol in symbols:
            if symbol not in self.contracts:
                raise KeyError(f"unknown contract: {symbol}")

    def _require_bar(
        self, bars: Mapping[str, MarketBar], symbol: str, timestamp: datetime
    ) -> MarketBar:
        bar = bars.get(symbol)
        if bar is None:
            self._missing(symbol, timestamp)
            raise ValueError(f"missing bar for {symbol} at {timestamp}")
        return bar

    def _missing(self, symbol: str, timestamp: datetime) -> None:
        if self.missing_data == "raise":
            raise ValueError(f"missing bar for {symbol} at {timestamp}")

    def _pnl(self, quantity: float, start: float, end: float, symbol: str) -> float:
        return quantity * (end - start) * self.contracts[symbol].multiplier

    def _make_fill(
        self, bar: MarketBar, quantity: float, raw_price: float, kind: str
    ) -> Fill:
        contract = self.contracts[bar.symbol]
        # The raw bar open/close is the accounting reference.  A quote
        # selects the executable side, then configured slippage moves it.
        reference = raw_price
        executable = bar.ask if quantity > 0 else bar.bid
        if executable is None:
            executable = raw_price
        price = executable + (
            self.slippage_ticks * contract.tick_size
            if quantity > 0
            else -self.slippage_ticks * contract.tick_size
        )
        slippage_cost = abs(quantity) * abs(price - reference) * contract.multiplier
        fee_cost = abs(quantity) * self.commission_per_contract
        cash_flow = -quantity * price * contract.multiplier
        return Fill(
            bar.timestamp,
            bar.symbol,
            quantity,
            price,
            reference,
            fee_cost,
            slippage_cost,
            cash_flow,
            kind,
        )
