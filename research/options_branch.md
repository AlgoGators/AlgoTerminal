# Options tail-protection branch for frozen CORE3

## Proposal

Keep CORE3 unchanged: `crack_321 + cross_sectional + bzwti`, equal weights,
and the existing signal, sizing, and drawdown overlay remain the control.
This branch tests a separate, defined-risk hedge sleeve.

The distinct hypothesis is that a small, continuously held, factor-mapped
put spread can cover an adverse overnight or limit move without buying the
whole book's variance. The earlier book-level monthly put test is not this
branch. That test used one synthetic put on the monthly book return and found
it uneconomic at modeled premiums.

The branch must be judged against two controls:

- CORE3 raw book, with the existing execution-cost and roll assumptions.
- CORE3 with the existing DD overlay and no options.

No CORE3 parameter, signal, weight, or overlay threshold may change.

## Instrument choice

Use options on listed futures as the primary implementation:

- CL options for the crude component.
- RB and HO options for refined-product components.
- BZ options for the Brent-WTI basis component when the `bzwti` exposure
  mapping requires it.

A listed crack-spread option is a possible simplification, but it is only
usable after contract specifications, historical settlements, volume, open
interest, and spread liquidity are verified. It must not be assumed from a
vendor symbol. The first modeled test therefore uses the leg options and
maps their payoff to the actual CORE3 factor exposures.

Buy a 25-35 delta put and sell a 5-10 delta put with the same expiry. Use
45-60 days to expiry and roll at a fixed 21 days to expiry. The short put
makes the hedge a bounded-loss spread and directly tests a cheaper structure
than the rejected naked crash put. The short strike is a reporting boundary,
not a claim that losses beyond it are safe.

Size the spread to cover 0.5x and 1.0x of the causal one-day adverse factor
shock. Size each leg from the frozen factor-return series and its current
contract multiplier. Do not size from future option prices or from the hedge
result.

## Gap-risk mechanism

CORE3 is long crushed-margin reversion. An energy shock can move crude and
products together before a daily circuit breaker or hard stop can execute.
A close-only stop reduces exposure after the gap and cannot insure the gap.
The hedge must already exist at the prior close.

For every day, calculate the frozen book's factor and leg deltas at close
t-1. Apply the next observed open-to-close and close-to-open leg moves to the
option payoff. A gap event is the close-to-open move, not a same-day close
return. Mark the hedge at the next available option observation, or use a
conservative intrinsic-plus-time-value proxy until option data exists.

The hedge is successful only if it reduces the loss of the combined book on
adverse gap days without removing the CORE3 windfall on favorable shock days.
Report both signs. A generic long-crude put is not automatically protection:
its sign must be checked against the realized CORE3 delta on 2020-04-20,
2020-03-12, 2019-09-03, and every other worst control day.

Use a pre-registered stress-state variant, not an after-the-fact date list.
The candidate state is either an always-on hedge or a hedge kept on through
the month after CORE3 enters a causal deepening state. The state uses only
t-1 data: rolling energy volatility, CORE3 drawdown, and five-day factor
crush acceleration. The always-on result is the clean cost control; the
state result tests whether timing lowers carry. No future return may choose
the state.

## Carry and economics

Carry is the paid spread premium, roll slippage, bid-ask cost, and any
margin or liquidity haircut. Report each separately and as annualized
percentage of protected notional. Model IV as lagged realized leg volatility
with 1.00x, 1.25x, and 1.50x markups. Add a fixed bid-ask haircut and a
stress haircut for wide markets.

The first pass has a hard economic screen:

- Always-on hedge: premium plus trading cost below 2.0% per year of book
  notional at the base markup.
- State hedge: premium plus trading cost below 1.0% per year.
- At least 50% reduction in worst gap-day loss and no more than 20% loss of
  CORE3 raw CAGR in the same test.

These are screening limits, not tuned targets. The prior stylized put cost
about 4.1% per year even at realized volatility and improved MaxDD only from
about -29% to -26%. If this spread cannot beat that trade-off, stop the
branch. Report cases that fail rather than relaxing the limits.

## Data requirements

The modeled screen can use the existing 2007-07-02 through 2026-09-09
panel and the frozen CORE3 daily factor returns. It must add:

- Contract-level CL, RB, HO, and BZ futures prices with expiry and roll
  dates, rather than treating a stitched close as a tradable contract.
- Historical option settlement or executable bid/ask data by strike,
  expiry, and timestamp.
- Contract multiplier, tick size, trading hours, expiry, exercise, and
  delivery rules.
- Open interest and volume to reject unexecutable strikes.
- Rates and collateral convention for Black-76 discounting.

Free yfinance chains are current-only and cannot support historical fills.
Until a historical option source is obtained, modeled prices are a
plausibility screen only. A real validation needs CME settlements or a
licensed historical option database, plus a documented roll and fill rule.

## Execution assumptions

Generate the hedge order after the t-1 close and fill at the next session's
mid plus the stated half-spread. Reject a trade when volume or open interest
is below the pre-registered minimum. Roll the old spread and open the new
spread at the same timestamp. Do not use intraday highs, lows, or closing
prices that were unavailable at order time.

Use one option spread per mapped leg, with net delta and contract rounding
shown in the output. Include commissions, exchange fees, half-spread, and
one extra stress case with doubled spread. Keep the option hedge separate
from the CORE3 execution ledger so its costs cannot disappear inside the
book return.

## Minimal historical test

1. Rebuild the existing panel and reproduce the frozen CORE3 raw and DD
   overlay controls before adding an option column.
2. Construct causal daily leg deltas from the frozen factor definitions.
3. For each expiry and delta pair, calculate Black-76 spread prices using
   lagged realized volatility and the three IV markups. Use 0.5x and 1.0x
   protection sizes.
4. Test four pre-registered variants: always-on spread, state-activated
   spread, each with base and doubled transaction costs. Do not sweep
   arbitrary triggers.
5. Apply option payoff to close-to-open gaps and regular daily moves. Compare
   CAGR, Sharpe, MaxDD, worst day, worst gap day, annual premium, turnover,
   and share of top-five positive days retained.
6. Produce event rows for 2020-04-20, 2020-03-12, and 2019-09-03, plus the
   five worst combined-book gap days. Show CORE3, hedge, and combined return.
7. Split the report at 2023-09-08 for a chronological diagnostic. Treat the
   result as contaminated research evidence, not an OOS claim, because CORE3
   and the historical screen were selected after inspecting this history.

The branch passes only if it reduces gap losses at a carry consistent with
the limits above and survives doubled spreads and a 1.25x IV markup. If it
fails, retain CORE3 with its existing DD overlay and record the options
branch as falsified for this construction. No live deployment follows from
the modeled test.
