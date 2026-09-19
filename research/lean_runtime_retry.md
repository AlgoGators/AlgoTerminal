# QuantConnect LEAN runtime retry

- Task: `retry-lean-runtime`.
- Run time: 2026-09-15 UTC.
- Host: WSL2 on `DESKTOP-5EU7DVK`, Linux `6.18.33.2-microsoft-standard-WSL2`, `x86_64`.
- Python: `3.12.3`.
- Project source was not changed.
- The five pre-existing tracked modifications and pre-existing untracked research files were left untouched.

## Installed versions

- Temporary .NET SDK: `10.0.100`.
- Temporary .NET runtime: `Microsoft.NETCore.App 10.0.0`.
- Temporary .NET SDK install path: `/tmp/retry-lean-runtime.2462502/dotnet10`.
- Public QuantConnect CLI package: `lean 1.0.229` from PyPI.
- Temporary CLI install path: `/tmp/retry-lean-runtime.2462502/cli`.
- CLI version output: `lean 1.0.229`.
- LEAN engine build: `v2.5.0.0`.
- Reused public QuantConnect Lean checkout commit: `f9107abdf26121c5ce159f561bd27fead01d30e1`.
- The checkout and all temporary installations stayed under `/tmp`.

## Exact installation and capability commands

```bash
TMP=/tmp/retry-lean-runtime.2462502
mkdir -p "$TMP"
python -m pip install --disable-pip-version-check --no-input --target "$TMP/cli" 'lean==1.0.229'
PYTHONPATH="$TMP/cli" "$TMP/cli/bin/lean" --version
curl -fsSL https://dot.net/v1/dotnet-install.sh -o "$TMP/dotnet-install.sh"
chmod +x "$TMP/dotnet-install.sh"
"$TMP/dotnet-install.sh" --version 10.0.100 --install-dir "$TMP/dotnet10" --no-path
"$TMP/dotnet10/dotnet" --version
"$TMP/dotnet10/dotnet" --info
```

The CLI reported `The Lean CLI by QuantConnect` and exposed the `backtest` command.
The official CLI uses Docker for local backtests.
Docker was not usable in this WSL2 distro because Docker Desktop WSL integration was not enabled.
The observed Docker error was `The command 'docker' could not be found in this WSL 2 distro.`
The CLI `init` command also requires a QuantConnect user id and API token when no organization is supplied.

## Smallest reproducible futures fixture

The fixture uses one ES E-mini contract over two trading dates.
The algorithm adds `Futures.Indices.SP500EMini` at minute resolution, selects the nearest contract, buys one contract on the first chain event, and liquidates on the next date.
The fixture source is `/tmp/lean-attempt.p9MR5W/Lean/Algorithm.CSharp/LocalFuturesFixtureAlgorithm.cs`.
The source SHA-256 is `cf65a39f5ef7d62afcb83574907a64fc033a4ddb22285a0fbd015735a80fd0eb`.
The LEAN configuration is `/tmp/lean-attempt.p9MR5W/config.json`.
The configuration SHA-256 is `5e39e6da1a4686a24b26b627482b43e2e424170eef34cf9b29a628235c5c99e3`.

Exact engine command:

```bash
cd /tmp/retry-lean-runtime.2462502
/tmp/retry-lean-runtime.2462502/dotnet10/dotnet \
  /tmp/lean-attempt.p9MR5W/Lean/Launcher/bin/Release/QuantConnect.Lean.Launcher.dll \
  --config /tmp/lean-attempt.p9MR5W/config.json
```

The command exited `0`.
The run completed with no runtime error.
LEAN processed `9,951` data points in `0.42` seconds.
The data monitor reported `19` successful data requests and `0` failed data requests.
The data monitor reported `3` successful universe requests and `0` failed universe requests.
The chain event was `2013-10-08 09:31:00` for one ES chain.
The selected contract was `ES20Z13` with internal symbol `ES VMKLFZIH2MTD`.
The entry fill was one contract at `1670.00` on `2013-10-08 09:31:00`.
The exit fill was one contract at `1652.25` on `2013-10-09 09:31:00`.
The fixture produced two orders and one losing round trip.
The gross contract loss was `-$887.50`.
Fees were `$4.30`.
The ending equity was `$999,108.20` from `$1,000,000.00`.
The run result file is `/tmp/retry-lean-runtime.2462502/LocalFuturesFixtureAlgorithm.json`.
The result file SHA-256 is `dc1e29fadd9752151742127c00b25ecc79124a51036f1bd88eee11cf24197011`.
The order event file is `/tmp/retry-lean-runtime.2462502/LocalFuturesFixtureAlgorithm-order-events.json`.
The order event file SHA-256 is `b42759ac4cc807ee646d650f6af6e93505e0d6a5054a3e0807356d05232f28a3`.

## Fixture data consumed

- ES minute trade data for `2013-10-07` through `2013-10-09`.
- ES minute quote data for `2013-10-07` through `2013-10-09`.
- ES minute open-interest data for `2013-10-07` through `2013-10-10`.
- ES futures universe files for `2013-10-07` through `2013-10-09`.
- ES margin data.
- SPY hourly and daily benchmark data.
- The local interest-rate file.
- The fixture data root was `/tmp/lean-attempt.p9MR5W/Lean/Data/`.
- The consumed-data manifest was `succeeded-data-requests-20260915210614011.txt`.

## Remaining requirements

- Docker Desktop WSL integration is required to run the public `lean backtest` wrapper directly.
- A durable fixture must preserve the LEAN source commit, algorithm source, configuration, and all listed local data files because the current files are temporary under `/tmp`.
- A strategy-level futures validation still needs contract-level CL, RB, HO, and BZ data rather than the single ES smoke fixture.
- That validation needs daily or minute trade and quote data, open interest, exchange calendars, futures universe files, map files, factor files, margins, settlements, and expiry metadata.
- It also needs explicit contract roll records and execution assumptions for fees, slippage, liquidity, and roll costs.
- The smoke result proves that the runtime can load local futures data and process orders.
- It does not validate the audit strategy or provide performance evidence for the crack-spread book.
