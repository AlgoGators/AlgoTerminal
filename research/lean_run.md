# LEAN capability probe

## Result

A full QuantConnect LEAN fixture did not run in this environment.

The deterministic probe returned:

```text
status=unavailable; missing=dotnet runtime, QuantConnect LEAN CLI, LEAN fixture data
```

The exact missing requirements are:

- `dotnet` is not installed or present on `PATH`.
- The QuantConnect LEAN CLI is not installed or present on `PATH`.
- The repository has no `lean_fixture/` data directory.

The `lean` executable under `/home/sebas/.elan/bin/lean` is Lean 4.34.0, the theorem prover.
It is not the QuantConnect LEAN CLI and does not satisfy the engine requirement.
`lean-cli` is also absent.

## Bounded fallback

`lean_runner.py` performs no network access, package installation, or data fabrication.
It checks the required runtime, distinguishes the QuantConnect CLI from the Lean theorem prover, and checks for local fixture data.
It reports `valid` only when all three requirements exist.

The fallback is deterministic because the test supplies the command lookup and fixture path.
It gives the same ordered missing-requirement report for the unavailable case.

## Reproduction

From this repository, run:

```bash
python lean_runner.py
pytest -q test_lean_runner.py
```

The focused test passes and verifies the exact unavailable result.
No LEAN engine result or trading performance claim is made.
