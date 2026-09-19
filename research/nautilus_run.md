# NautilusTrader futures run

## Result

The tiny run completed in an isolated temporary virtual environment.

The environment pinned `nautilus_trader==1.231.0` from a binary wheel.

The engine reported a valid run with three filled market orders.

The project environment does not install NautilusTrader.

The runner therefore returns `unavailable` when the optional package is absent and preserves engine errors as `failed`.

The isolated run returned:

```text
NautilusResult(status='valid', fill_probability=1.0, slippage_probability=0.0, contracts=('CLF25', 'CLG25'), fills=3, gross_pnl=None, error=None)
{'gross_pnl': 2000.0, 'roll_cost': 1000.0, 'net_pnl': 1000.0, 'fills': 3, 'rolls': 1}
```

The Nautilus result has no PnL value because this spike records execution fills only.

## Reproduction

Run these commands from the audit repository.

```bash
tmp=$(mktemp -d /tmp/nautilus-run.XXXXXX)
python -m venv "$tmp/venv"
"$tmp/venv/bin/pip" install --only-binary=:all: nautilus_trader==1.231.0
PYTHONPATH="$PWD" "$tmp/venv/bin/python" - <<'PY'
from nautilus_runner import run_fixture, compare_with_contract_adapter
print(run_fixture(fill_probability=1.0, slippage_probability=0.0))
print(compare_with_contract_adapter())
PY
```

The temporary environment is not part of this repository.

## Fixture coverage

The fixture has `CLF25` with root `CL`, expiry `2025-01-20`, multiplier `1,000`, and tick size `0.01`.

It has `CLG25` with root `CL`, expiry `2025-02-20`, multiplier `1,000`, and tick size `0.01`.

The explicit transition is `2025-01-10 UTC`, from `CLF25` to `CLG25`, with reason `scheduled`.

The runner creates both Nautilus `FuturesContract` instruments with activation and expiration timestamps.

The runner sends an old-contract buy, an old-contract sell, and a new-contract buy at the transition.

The runner configures Nautilus `FillModel` with `prob_fill_on_limit=1.0`, `prob_slippage=0.0`, and `random_seed=7`.

The fixture uses daily OHLC bars and does not claim intrabar execution realism.

## Reference comparison

`contract_adapter.py` reports gross PnL of `2,000.00`, roll cost of `1,000.00`, and net PnL of `1,000.00`.

Its three fills are one target fill plus two roll fills.

The reference target fills at the first bar strictly after the decision timestamp.

The reference roll closes the old contract at its bar close and opens the new contract at its bar open.

## Comparison validity

A performance comparison is **not valid** from this run.

The Nautilus spike proves that dated instruments, explicit transitions, and configurable fill settings can be wired into its event engine.

It does not prove that Nautilus and `ContractAdapter` applied the same fill timestamps or accounting rules.

The Nautilus strategy submits market orders from bar callbacks, while `ContractAdapter` applies next-bar target fills and same-bar old-close/new-open roll fills.

The spike does not collect Nautilus realized or unrealized PnL, commission, slippage, margin, or roll cash-flow decomposition.

The fixture is synthetic and too small for a performance claim.

A valid comparison needs one shared order and fill event ledger, matched commission and slippage models, matched mark and roll accounting, and a raw multi-contract dataset.

## Verification

The focused tests pass with `pytest -q test_nautilus_runner.py`.

The report exists and is non-empty with `test -s research/nautilus_run.md`.
