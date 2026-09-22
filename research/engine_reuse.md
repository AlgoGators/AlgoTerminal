> **CORRECTION (2026-09-22, independent audit).** Every statement in this
> document that describes the yfinance price panel as "back-adjusted" is
> WRONG. `CL=F/BZ=F/RB=F/HO=F` are raw front-month continuous series with the
> roll gaps intact. Proof: the 3:2:1 crack built from them gains
> **+3.915 $/bbl on the first trading day of March, in 18 of 18 years**, and
> repays it across the other eleven months; month-start jump ratio is 2.06x.
> Those sessions were **40.2%** of the measured walk-forward P&L. The roll
> jumps were never removed, so they were booked as profit. On roll-free spot
> prices, at measured cost, the edge is not statistically significant.
> Full record: `algoterminal-strategy-v2/findings/artifact_audit.md`.

# Engine reuse research

## Scope and conclusion

The audit repo has a useful research pipeline, but its production backtest contract is still a daily-price shortcut.
The minimum safe path is to keep the current signal code and replace only the portfolio accounting seam with a contract-aware adapter.
Use LEAN as the primary candidate for contract-level futures and paper trading.
Use NautilusTrader as the stronger alternative when event-driven execution and live/paper parity matter more than a small migration.
Do not make vectorbt or the current vectorized engine the source of truth for rolls and fills.

This is a local inspection.
The installed Python environment exposes `pandas 3.0.5`, `numpy 2.5.2`, `yfinance 1.6.0`, and `pyarrow 25.0.1`.
No `vectorbt`, `backtrader`, `zipline-reloaded`, `bt`, `nautilus-trader`, `ib_insync`, `backtesting`, `qstrader`, `hftbacktest`, or `rqalpha` distribution was found, and no matching CLI was found.
These engines remain open-source candidates, not installed dependencies.

## Current reuse points

- `src/algoterminal/data/provider.py` already defines a normalized `DataProvider` and concurrent `fetch_many`.
- `src/algoterminal/data/yfinance_provider.py` supplies OHLCV through a cache, but `yfinance` futures symbols such as `CL=F` are continuous front-month observations rather than a contract ledger.
- `harness.py` already fetches a CL/RB/HO panel and passes the full panel into a multi-leg strategy.
- `strategy_v4.py` is a clean strategy seam: `generate_signals`, `size_positions`, `apply_risk_rules`, and public `leg_levels`.
Its seasonal z-score, long-only state machine, per-leg volatility sizing, trailing stop, circuit breaker, hard stop, and cooldown can remain strategy logic.
- `engine_v2.py` documents the key data limitation and already has explicit stub-versus-proxy roll streams, per-leg turnover cost, stress widening, gap caps, and risk overlays.
Its roll proxy is not a contract-level roll model, but its comparison output is reusable as a validation baseline.
- `long_backtest.py` has a small cost seam: per-leg turnover multiplied by trade bps plus an annual roll drag.
Use it to make before/after comparisons, not as final futures accounting.
- `src/algoterminal/research/backtest.py` has the narrowest replacement point.
It currently assumes one `Series`, computes `position.shift(1) * pct_change()`, and has no fill, cash, multiplier, margin, expiry, or roll state.
- `imc4/backtesting/run_local.py` and `imc4/scripts/backtester.py` contain reusable event-loop ideas: order-book snapshots, maker/taker distinction, own-price passive fills, partial-fill limits, cash and position tracking, mark-to-market, and fill diagnostics.
They target Prosperity toy products and integer ticks, so they are not a futures engine.

## Contract-level requirements exposed by the audit

A replacement must represent a contract as symbol, venue, expiry, multiplier, tick size, currency, margin metadata, and trading calendar.
It must retain individual contract bars or quotes instead of only a continuous series.

It must support a deterministic roll policy, such as days-before-expiry, volume/open-interest switch, or calendar spread.
The roll event needs two fills, old-contract close and new-contract open, with bid/ask or spread costs and a persisted roll reason.
Back-adjusted research prices may be used for signal features only.
PnL and cash must use raw contract prices, contract multipliers, and explicit roll cash flows.

It must define fill timing and order semantics.
At minimum, support next-bar market fills, limit/stop eligibility, partial fills, bid/ask spread, configurable slippage, commissions, and missing-quote behavior.
Daily OHLC data cannot prove intrabar stop ordering, so that limitation must be recorded or tested with a conservative rule.

It must track margin, buying power, mark-to-market variation, realized and unrealized PnL, and forced liquidation.
It must expose an event stream or fill ledger that can be audited against the strategy decision at each timestamp.
Paper trading must use the same order and risk interfaces as replay, with a broker adapter and reconciliation of submitted, acknowledged, filled, canceled, and rejected orders.

## Candidate engines

| Candidate | Futures, rolls, fills, slippage | Paper/live | Fit and cost |
|---|---|---|---|
| **LEAN (QuantConnect)** | Strong contract universe and futures canonical/continuous-symbol model; configurable fee, fill, slippage, buying-power, margin, and brokerage models | Strong; paper brokerage and many broker integrations | Best all-round target for a contract-aware backtest and paper path. Requires a .NET/LEAN runtime, data adapter work, and translating the Python strategy contract into LEAN algorithm callbacks or a bridge. Check current license and brokerage/data terms before adoption. |
| **NautilusTrader** | Strong event-driven instrument model, futures contract metadata, order matching, fills, commissions, slippage, and exchange-style simulation | Strong live and paper architecture | Best technical fit for one event model from replay to paper. It is a larger rewrite, has native/compiled components, and needs a market-data and broker adapter. Validate current API and license at pin time. |
| **Backtrader** | Mature commission and slippage hooks and broker simulation; rollover feeds can join contract streams, but contract lifecycle and exchange margin semantics need custom code | Some broker integrations and live stores | Lowest rewrite for a bar-driven prototype. It is not sufficient by itself for reliable contract-level rolls or realistic order-book fills. Use only behind a custom futures feed/broker and keep the fill ledger. |
| **vectorbt** | Excellent fast array research; fees, slippage, and order simulation are available, but contract expiry/roll lifecycle and margin are application code | Not a paper-trading system | Useful for parameter sweeps and regression comparisons. Keep it as a research accelerator, never the accounting authority. It is not installed here. |
| **Zipline Reloaded** | Calendar-aware equities research and commission/slippage abstractions; futures support and contract lifecycle are not a strong fit for this audit | No direct paper execution path | Not recommended for the futures objective. Migration would add more custom lifecycle work than it removes. |
| **hftbacktest** | Excellent tick/order-book replay and queue-aware fill modeling | No general paper broker layer | Worth considering only if tick data and queue position become requirements. It does not solve contract rolls or portfolio margin alone. |

Open-source components should be evaluated by pinned commit/version, license, data-license compatibility, Python/NumPy compatibility, and whether the futures adapter is maintained.
No candidate should be added to `pyproject.toml` until a small contract-and-fill spike passes.

## Integration seams

1. Add a `ContractDataProvider` beside `DataProvider`.
Return a contract table and raw bars/quotes keyed by `(root, expiry)`.
Keep the existing provider for research features and public data.
2. Add a neutral strategy input/output adapter.
Translate the existing panel into a `MarketSnapshot` and translate `strategy_v4`'s per-leg target positions into target quantities for CL, RB, and HO contracts.
Preserve the existing shifted-signal behavior.
3. Add a `RollPolicy` and `ContractResolver`.
Resolve the active contract per root, emit a roll event, and persist old/new symbols, timestamp, reason, and quantities.
Do not infer rolls from a close series that has been back-adjusted. (Note: the
local yfinance panel is raw front-month, not back-adjusted, so rolls ARE visible.
4. Add an execution model interface with `submit`, `match`, `cancel`, `commission`, and `slippage` hooks.
The imc4 fill loop can supply test fixtures for market, limit, passive, partial, and rejected orders.
5. Add a ledger adapter.
Emit fills and daily marks into the existing `BacktestResult` shape so charts, stats, writeups, and CSV/parquet outputs keep working.
Include gross PnL, trading cost, roll cost, slippage, commission, margin, and net PnL as separate fields.
6. Add a paper broker adapter.
Feed live snapshots into the same target-to-order and risk path, then reconcile broker events into the ledger.
The current TUI is a report viewer, not a paper execution surface.

## Missing dependencies and data

- No contract-aware futures engine is installed.
- `pyproject.toml` has `pandas`, `numpy`, `scipy`, `yfinance`, and `pyarrow`, but no broker SDK, exchange calendar package, contract master, or execution simulator.
- `yfinance` supplies delayed continuous futures closes used by `engine_v2.py`; it does not provide the adjacent raw contract history, official settlement, reliable volume/open-interest roll rule, or executable bid/ask history required here.
- A real migration needs contract metadata and raw histories for CL, RB, HO, and later BZ and NG, including expiry, first notice/last trade, multiplier, tick, settlement, volume/open interest, and calendar.
- It also needs a defined source for quotes or bid/ask bars, commission schedule, slippage assumptions, exchange/clearing margin, and a paper broker credential/configuration path.
- Official settlement and historical adjacent-contract data remain explicit gaps already recorded in `engine_v2.py` and `RESEARCH_FINDINGS.md`.

## Minimum migration plan

1. Freeze current outputs by running `harness.py`, `long_backtest.py`, and `engine_v2.py --smoke`.
Record the current gross result and the existing stub/proxy roll comparison.
2. Build a tiny local contract fixture for two expiries and three bars.
Write failing checks first for multiplier PnL, next-bar fills, bid/ask slippage, partial fills, and a roll that closes the old contract and opens the new one.
3. Implement the ledger and resolver behind the existing `run_backtest` boundary.
Run the fixture before using external data.
4. Port only `strategy_v4.py` through the adapter.
Compare signal dates and target exposures against `harness.py` before comparing PnL.
5. Load a short raw CL/RB/HO contract sample and validate roll dates, quantities, cash, margin, and cost decomposition.
Keep continuous-price results as a labeled research baseline.
6. Run a 10-year walk-forward with at least zero-cost, base-cost, and widened-slippage cases.
Require an auditable fill ledger and no unexplained divergence from the baseline.
7. Add paper mode only after replay and reconciliation checks pass.
Start with a no-submit shadow mode, then a broker sandbox, then a capped paper account.

**Recommendation:** prototype the adapter against LEAN if the goal is the smallest path to contract-aware futures plus paper trading.
Choose NautilusTrader instead if live execution and one event-driven model are first-order requirements.
Keep the existing pandas engine and imc4 fill code as deterministic comparison fixtures, not as the final futures runtime.
