"""Contract accounting spike fixtures.

These tests define the small neutral seam used by a later broker or engine
adapter: raw contract bars in, target quantities and roll instructions in,
and an auditable fill/PnL ledger out.
"""
from datetime import date, datetime

import pytest

from contract_adapter import Contract, ContractAdapter, MarketBar, Roll, Target


def test_raw_contract_pnl_uses_contract_multiplier():
    contract = Contract("CLH25", root="CL", expiry=date(2025, 3, 20), multiplier=1_000)
    bars = [
        MarketBar(datetime(2025, 1, 2), "CLH25", open=70.0, close=70.0),
        MarketBar(datetime(2025, 1, 3), "CLH25", open=70.0, close=72.0),
        MarketBar(datetime(2025, 1, 6), "CLH25", open=72.0, close=72.0),
    ]
    result = ContractAdapter({contract.symbol: contract}).run(
        bars, [Target(datetime(2025, 1, 2), "CLH25", 2), Target(datetime(2025, 1, 3), "CLH25", 0)]
    )

    assert result.gross_pnl == pytest.approx(4_000.0)
    assert result.net_pnl == pytest.approx(4_000.0)
    assert result.rows[1].gross_pnl == pytest.approx(4_000.0)


def test_target_is_filled_at_the_next_bar_open():
    contract = Contract("ESH25", root="ES", expiry=date(2025, 3, 21), multiplier=50)
    bars = [
        MarketBar(datetime(2025, 1, 2), "ESH25", open=4_000.0, close=4_010.0),
        MarketBar(datetime(2025, 1, 3), "ESH25", open=4_020.0, close=4_025.0),
    ]
    result = ContractAdapter({contract.symbol: contract}).run(
        bars, [Target(datetime(2025, 1, 2), "ESH25", 1)]
    )

    assert len(result.fills) == 1
    assert result.fills[0].timestamp == datetime(2025, 1, 3)
    assert result.fills[0].price == pytest.approx(4_020.0)
    assert result.rows[0].gross_pnl == pytest.approx(0.0)
    assert result.rows[1].gross_pnl == pytest.approx(250.0)


def test_roll_records_old_close_new_open_cash_flows_and_cost_separately():
    old = Contract("CLF25", root="CL", expiry=date(2025, 1, 20), multiplier=1_000)
    new = Contract("CLG25", root="CL", expiry=date(2025, 2, 20), multiplier=1_000)
    bars = [
        MarketBar(datetime(2025, 1, 9), "CLF25", open=70.0, close=70.0),
        MarketBar(datetime(2025, 1, 10), "CLF25", open=70.0, close=71.0),
        MarketBar(datetime(2025, 1, 10), "CLG25", open=72.0, close=72.0),
        MarketBar(datetime(2025, 1, 13), "CLG25", open=72.0, close=73.0),
    ]
    adapter = ContractAdapter({old.symbol: old, new.symbol: new})
    result = adapter.run(
        bars,
        [Target(datetime(2025, 1, 9), "CLF25", 1)],
        rolls=[Roll(datetime(2025, 1, 10), "CL", old.symbol, new.symbol)],
    )

    assert len(result.rolls) == 1
    roll = result.rolls[0]
    assert roll.old_close_cash_flow == pytest.approx(71_000.0)
    assert roll.new_open_cash_flow == pytest.approx(-72_000.0)
    assert roll.cash_flow == pytest.approx(-1_000.0)
    assert roll.cost == pytest.approx(1_000.0)
    assert result.gross_pnl == pytest.approx(2_000.0)
    assert result.roll_cost == pytest.approx(1_000.0)
    assert result.fee_cost == pytest.approx(0.0)
    assert result.slippage_cost == pytest.approx(0.0)
    assert result.net_pnl == pytest.approx(1_000.0)


def test_fees_and_slippage_are_separate_from_contract_pnl():
    contract = Contract(
        "NGH25", root="NG", expiry=date(2025, 2, 20), multiplier=10_000, tick_size=0.01
    )
    bars = [
        MarketBar(datetime(2025, 1, 2), "NGH25", open=3.0, close=3.0, bid=2.99, ask=3.01),
        MarketBar(datetime(2025, 1, 3), "NGH25", open=3.2, close=3.4, bid=3.19, ask=3.21),
    ]
    result = ContractAdapter(
        {contract.symbol: contract}, commission_per_contract=2.5, slippage_ticks=1
    ).run(bars, [Target(datetime(2025, 1, 2), "NGH25", 1)])

    assert result.fee_cost == pytest.approx(2.5)
    assert result.slippage_cost == pytest.approx(200.0)
    assert result.gross_pnl == pytest.approx(2_000.0)
    assert result.net_pnl == pytest.approx(1_797.5)
    assert result.fills[0].price == pytest.approx(3.22)


def test_unknown_contract_is_rejected():
    with pytest.raises(KeyError):
        ContractAdapter({}).run(
            [MarketBar(datetime(2025, 1, 2), "MISSING", open=1.0, close=1.0)], []
        )
