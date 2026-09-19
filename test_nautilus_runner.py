from datetime import date, datetime, timezone

import pytest

from nautilus_runner import (
    Fixture,
    build_fixture,
    compare_with_contract_adapter,
    run_fixture,
)


def test_fixture_has_dated_contracts_and_explicit_transition():
    fixture = build_fixture()

    assert fixture.contracts[0].expiry == date(2025, 1, 20)
    assert fixture.contracts[1].expiry == date(2025, 2, 20)
    assert fixture.transitions == ((
        datetime(2025, 1, 10, tzinfo=timezone.utc),
        "CLF25",
        "CLG25",
        "scheduled",
    ),)
    assert all(contract.multiplier == 1_000 for contract in fixture.contracts)


def test_reference_comparison_uses_the_same_tiny_fixture():
    fixture = build_fixture()
    reference = compare_with_contract_adapter(fixture)

    assert reference["gross_pnl"] == pytest.approx(2_000.0)
    assert reference["roll_cost"] == pytest.approx(1_000.0)
    assert reference["net_pnl"] == pytest.approx(1_000.0)
    assert reference["fills"] == 3
    assert reference["rolls"] == 1


def test_run_result_records_fill_configuration_and_status():
    result = run_fixture(fill_probability=1.0, slippage_probability=0.0)

    assert result.fill_probability == 1.0
    assert result.slippage_probability == 0.0
    assert result.status in {"valid", "unavailable", "failed"}
    if result.status == "valid":
        assert result.fills >= 3
        assert result.contracts == ("CLF25", "CLG25")


def test_invalid_fill_configuration_is_rejected():
    with pytest.raises(ValueError):
        run_fixture(fill_probability=1.1)
    with pytest.raises(ValueError):
        run_fixture(slippage_probability=-0.1)
