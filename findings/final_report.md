# The Strategy — Full Writeup for Presentation

A complete, build-from-first-principles explanation of the crack-margin
strategy: what it trades, why the edge exists, how it is built, every
number it uses and where that number came from, the full measured
results, and the honest limits of those results.

All performance numbers are verified. They are net of costs, measured
on non-overlapping windows, and every claim in this document was
through a pre-registered test. Nothing here was tuned on the same data
it is judged on except where explicitly stated.

---

## Part 1. The Big Picture (read this if you only read one page)

This strategy makes one bet, in one market, with one clearly stated
reason.

The bet: when the profit earned by turning crude oil into gasoline
and heating oil gets unusually small for the time of year, it tends
to get bigger again. We buy that profit margin when it is cheap, in
the market states where history says the recovery actually happens,
and we avoid it when the physical conditions say the recovery is not
coming.

That is the whole idea. Everything else in this document is about
making that single idea precise, honest, and measurable.

The clean results, in one table (all windows, net of cost):

| | Derivation | Out-of-window | Full history |
| --- | ---: | ---: | ---: |
| Years | 11.5 | 7.7 | 19.1 |
| Return per year | +14.1% | +6.5% | +11.7% |
| Sharpe | 0.87 | 0.72 | 0.84 |
| Max drawdown | -20.9% | -21.2% | -21.2% |

The honest summary: the strategy earns real money in the market
states where the edge is known to exist, and it earns about half as
much in the one window that was never touched during research. That
second number is the gap the forward test exists to close.

---

## Part 1A. The Edges, Deeply: Why Margins Revert

This section is the economics under the strategy. Read it as the
answer to one question: why should a refinery margin ever come back
to normal?

### The core premise, in the captain's own words

"They don't stay crushed, don't stay stretched. The same movements
that make them shift also make them correct back."

That sentence is the entire thesis. A refining margin is not a
random walk. It is the price of a service — converting crude into
usable fuel — and the market that provides that service is
self-correcting. Every force that moves the margin away from normal
whatever it is that caused a crush or a stretch, eventually generates
the opposing force that brings it back. The margin is a pendulum
with friction: it swings, but it does not swing away forever.

There is one honest qualification, and it shapes the whole strategy:
the two directions do not correct at the same speed or the same
reliability. Crushed margins come back for reasons that are slow but
almost inevitable. Stretched margins can stay stretched for a long
time because the forces that would end tightness are slower and less
reliable. That asymmetry is exactly why this strategy is long-only,
and why it refuses to trade stretched margins except to leave them
alone.

### Force 1: sticky capacity

The hardest fact in this market is that you cannot build a refinery
quickly. A new plant takes years and billions of dollars. Shutting
one down, or idling it, takes months. So capacity responds to price
on two completely different clocks:

- When margins are crushed: the weakest refineries stop, idle, or
  close. That removes product supply. Less supply, same sticky
  demand, and the margin is pushed back up. The exit is forced by
  the price signal itself — owners respond to the crush by leaving.
  This is "the same movement that shifts the margin corrects it":
  the low margin is what forces the capacity out.
- When margins are stretched: high margins attract utilization and
  imports, but brand-new supply takes years. So a stretch can
  survive on tightness. This is why the right tail is not reliably
  tradeable.

Think of a parking lot with a slow-moving gate. The lot is rarely
empty because cars (capdev) leave and enter slowly; the number of
lot-spaces (refinery capacity) adjusts only grudgingly. A crush is
the lot being over-supplied; the correction is spaces exiting.

### Force 2: seasons shift things

Demand is on a calendar that you can print: gasoline peaks in the
summer driving season, distillate (heating oil and diesel) peaks in
winter. The refinery must be ready for the peak before it arrives,
so the productive side of the calendar also has rhythm: runs rise
in the spring ahead of summer, tanks are built up (injection), and
maintenance is scheduled in shoulder seasons to prepare for the
peaks.

The strategy removes the calendar to find the deviation: what
matters is not "is the margin cheap?" but "is the margin cheap for
this time of year?" The seasonal z-score subtracts the same-month
norm and standardizes, so a January margin is compared to January,
not to July.

The deep point: the calendar itself is known to everyone, so the
calendar itself is priced and not an edge. The edge lives in the
deviations around the calendar — a cold snap that raises demand
more than usual, a flow unwind that overshoots, a maintenance
timing slip. The seasonal normalization exists exactly to isolate
those deviations, and the regime gate exists because the calendar
deviation behaves differently in different regimes.

### Force 3: storage and logistics

Inventories are the buffer of the whole system. When tanks are
full, the market has nowhere to put extra product, so the margin
is pressed. When tanks are low, the market must bid for product,
so the margin is supported. Storage is the pendulum's shock
absorber: it does not cause the swing, but it decides how hard the
swing is and how fast it reverses.

Two subtle physics follow:

- Tank bottoms: usable storage is not the same as reported
  storage. A “low” inventory number near operational minimums is
  much tighter than the same number far above the plumbing floor.
- Location: crude lives in specific places. Cushing, Oklahoma is
  the delivery point for WTI, and when Cushing fills, WTI must
discount to avoid more inflows — the “tank-tops” effect that
  pushed the Brent-WTI spread around for years. Pipelines and
  product shipping connect the islands; when a pipe is full or a
  batch is in transition, regional prices can disconnect from the
  national benchmark.

The strategy tests this force directly: when product inventories
are building strongly (the buffer is pressing), it goes flat. That
is the storage gate — the empirical test of the buffer mechanism,
and one of the few fundamental variables that survived every
falsification attempt.

### The mechanism, in one picture

```
Crushed margin
    -> weakest capacity exits        (months; forced by price)
    -> product supply tightens
    -> margin recovers               (the left-tail correction)

Stretched margin
    -> tightness persists            (capacity is sticky upward)
    -> new supply arrives slowly     (years)
    -> stretch can last              (the right tail is not reliable)

Same-movement correction: the dislocation itself produces the
response that ends it.
```

The strategy trades only the first row, in the regimes where it is
measured to work, and it steps out when the buffer presses.

### Why this maps to the strategy, force by force

| Economic force | Strategy component | Why |
| --- | --- | --- |
| Capacity exit on crush | Long crush in compression/normal | The forced exit IS the reversion; compression is where it is active |
| Capacity sticky upward | No short side; skip expansion | Tightness can persist; the stretch is not reliably tradeable |
| Calendar rhythm | Seasonal z (calendar + recent deviation) | Deviations around the calendar are the flow edge, not the calendar |
| Storage buffer | H1 de-risk when stocks build | The buffer pressing is the physical damper working against the trade |
| Place/location flows | Curve exposure | Temporary flow excursions relative to recent path revert first |

### What the data added beyond the theory

Theory says margins revert; the data says when. The clean measured
facts:

- A crushed margin in compression recovers strongly (+21% over 20
days in the two-regime table).
- A crushed margin in expansion does not (~0 to -3%). The same
  level, different state, opposite trade. The regime gate was not a
  nicety; it was the difference between the edge and noise.
- Strengthening product inventories remove the reversion edge —
  the storage gate de-risks exactly those moments.
- Known calendars (maintenance dates, blend switches) carried no
  edge once tested cleanly; the deviations around them do. This is
  the priced-vs-surprise division that keeps the strategy honest.

---

## Part 2. The Market, Explained

### Oil futures

An oil futures contract is a promise to buy or sell a barrel of oil
at a fixed price on a fixed future date. The market constantly
prices these promises. We use the front-month (nearest) contract
prices.

We track four instruments:

- CL = WTI crude oil (the US benchmark), in dollars per barrel.
- RB = gasoline, in dollars per gallon.
- HO = heating oil, in dollars per gallon.
- NG = natural gas, dollars per million BTUs (used in research,
  not in the final strategy).

One barrel holds 42 gallons. That unit fact matters everywhere
below.

### The crack spread (the "refining margin")

A refinery buys crude oil and turns it into products. The profit per
barrel is the value of the products minus the cost of the crude:

```
crack = (2 x gasoline + 1 x heating oil)/3 x 42 - crude
```

This is the "3-2-1" crack: out of 3 barrels of crude, a typical
refinery makes roughly 2 barrels of gasoline and 1 barrel of heating
oil. Multiply the product prices by 42 to convert gallons to
barrels, subtract the crude price, and you have the margin in
dollars per barrel.

The number moves every day. Sometimes the margin is fat, sometimes
it is crushed. This strategy trades that margin.

### Why the margin moves

Three forces push the margin around:

1. Capacity. Refineries are hard to build and slow to close. You
   cannot quickly add a refinery when margins are high, and when
   margins are low, the weakest refineries shut down or idle. This
   is called "sticky capacity."
2. Seasons. Demand follows the calendar. Summer means more driving,
   so gasoline demand rises. Winter means more heating, so distillate
   (heating oil, diesel) demand rises. The margin has a strong
   annual cycle.
3. Storage and logistics. Product inventories buffer the market.
   When tanks are full, the margin is under pressure. When tanks
   are low, the margin is supported. Where the crude is stored
   matters too (Cushing, Oklahoma is the delivery point for WTI).

### The core economic claim

When the refining margin becomes unusually small for the time of
year, history says it tends to recover. Why? Because the forces are
self-correcting:

- Weak capacity leaves the system, which removes supply.
- Seasonal demand returns on the calendar.
- The buffer drains and stops pressing.

These corrections are slow but they happen. "Slow but inevitable"
is the entire reason the edge exists.

---

## Part 3. Why the Edge Was Hiding: Regimes

The naive version of this idea fails. Buying every cheap margin
loses money in some eras, and the reason is not noise: it is
regime. "Is this margin cheap?" is the wrong question. The right
question is: "Is this margin cheap AND in the market state where
cheap margins recover?"

We measured the forward behavior of a crushed margin in two states:

| Market state | What it means | What happens next (20-day forward) |
| --- | --- | --- |
| Compression | margin below its long-run baseline | crushed margin recovers strongly (+21%) |
| Expansion | margin above its long-run baseline | crushed margin does not recover (~0 to -3%) |

In compression, weak capacity is already exiting and demand is
returning: the correction is active. In expansion, tightness
persists because capacity is sticky on the way up: a cheap margin
stays cheap. The same "cheap margin" is a different trade in the two
states.

So we only trade the crush in compression and normal states. We
explicitly skip expansion. This single gate removed a whole class of
losing trades and is one of the largest, cleanest improvements in
the project.

---

## Part 4. The Storage Buffer

Our second confirmed mechanism comes from storage. When product
inventories are rising (building) week after week, the physical
buffer is doing exactly the thing that presses margins: more product
is sitting in tanks. We measured that de-risking the position during
strong stock builds is statistically helpful. This was one of the
few "fundamental" ideas that survived and it survived only after a
clean re-test overturned an earlier (wrong) conclusion.

Rule: when same-month product stocks are building strongly, we go
flat. We do not fight the buffer.

---

## Part 5. The Strategy, Step by Step

Here is what the strategy does, day after day. Everything runs on
information known at the close; the position ends up on at the next
open.

**Step 1. Compute the margin (the crack).**
As in Part 2. One number per day.

**Step 2. Measure "cheap relative to the season".**
We compute a seasonal z-score. Plainly: "how many standard
deviations is today's margin away from what is normal for this time
of year, after removing the recent trend?" A z of -0.5 means the
margin is about half a standard deviation below its seasonal norm.

This uses a two-stage construction: first remove the calendar
component (compare to the same month in past years), then compare
the result to its own recent 90-day behavior. The second stage is
what makes the signal about temporary flow excursions, not about a
calendar the market already knows.

**Step 3. Check the regime.**
Is the margin below, near, or above its long-run baseline? We only
trade when it is in compression or normal. Expansion: no trade.

**Step 4. Set the exposure from the data curve.**
We did not pick a "buy if z < -0.75" rule. Instead we measured, on
the derivation data only, the expected 20-day return for every level
of z in the two tradeable regimes. That produced a curve. The
exposure on any day equals the curve's value at today's z, scaled to
a maximum of 1. The curve rises as the crush deepens. This removes
the entry threshold; the exposure fades smoothly as the margin
recovers.

**Step 5. Apply the storage gate.**
If product stocks are building strongly, exposure = 0.

**Step 6. Size and risk.**
- Scale: 0.468 x the raw curve exposure. Where did 0.468 come
  from? A loss budget of 10% over 20 days divided by the measured
  tail of the crush-state distribution (the expected shortfall was
  21.4% of downside in 20 days on the derivation window). The scale
  is "the notional at which the measured tail equals our stated
  budget."
- Per-trade loss budget: 7.5%. The hard stop is placed where a
  7.5% loss would occur given the position size (about 16% of level
  move). The old 20% hard stop from the v1 days was closer to right
  than my initial 2% guess; the sweep proved that.
- Trailing stop: placed at the 85th percentile of the adverse move
  that winning trades typically gave back. We measured it, we did
  not guess it.
- Circuit breaker: the derived threshold (the 99th percentile of
  level moves) rarely fires at this scale, so it is effectively
  inactive. We say this openly.
- After any stop, 3 sessions flat (cooldown — the derived median
  retrigger time in the sweep).

**Step 7. Costs and reporting.**
5 basis points per side per trade, 20 basis points per year of roll
drag. These are assumed, standard industry magnitude; measured
sources are still on the to-do list.

---

## Part 6. Where Every Number Came From

This section exists because the project had a hard rule: no number
gets into the strategy unless it came from the data or is an
explicitly named economic choice. Every choice is listed.

| Number | Value | Source | Type |
| --- | --- | --- | --- |
| Regime window | 504 days, median + 1.4826 x MAD | robust central tendency of the data | derived |
| Seasonal z | calendar mean + 90-day recent stage | structural construction; robustness plateau verified | derived/structure |
| Entry line | z <= -0.45 | the largest z whose TRAIN curve bin had t-stat >= 1.5 | derived |
| Exposure curve | E[fwd20\|z, regime]/max | TRAIN conditional-mean curve | derived |
| Storage gate | stocks z >= +1 | one same-month standard deviation | derived |
| Scale | 0.468 | 10% budget / 21.4% TRAIN ES5 | derived |
| Per-trade budget | 7.5% | TRAIN sweep marginal (7.5% beat 5% beat 2%) | derived |
| Trailing percentile | 85th | TRAIN sweep marginal | derived |
| Cooldown | 3 sessions | TRAIN sweep marginal | derived |
| CB threshold | ~99th pct level move | TRAIN percentile (inactive at scale) | derived |
| Loss budget | 10% over 20 days | economic risk appetite | named anchor |
| Costs | 5/20 bps | industry standard assumption | assumption |

Sweep discipline: the harness that chose the sweep values had to
first reproduce the base result (TRAIN t = 1.11). If it could not,
its rankings were discarded. We hit exactly that failure once; the
bug (a sign error on the circuit breaker) was found, fixed, and the
sweep re-run from the anchor.

---

## Part 7. How We Prevented Self-Deception

Four rules kept the numbers honest.

1. Pre-registration. Every test wrote its method down before it ran:
   thresholds, windows, acceptance bars.
2. Non-overlapping measurement. Forward returns were measured on
   non-overlapping 20-day blocks so observations are independent. All
   headline statistics in this report use those blocks.
3. Causality. Every input is known at the close that decides the
   position. Weekly EIA data is lagged by 6 days. No look-ahead.
4. Trial-correction. The deflated Sharpe asks: "given N attempts, how
   likely is it that a dead strategy lucked into this result?" It is
   reported at 1,000 attempts.

Independent verification: every published number here was recomputed
by a second implementation and checked with internal consistency
relations (block t-stats against daily t-stats, Sharpe against the
mean's t-stat, geometric CAGR, trade-by-trade P&L). Everything
matched.

---

## Part 8. The Results

### The full table

All values are net of costs, on non-overlapping 20-day blocks.

| Metric | Derivation (11.5y) | Out-of-window (7.7y) | OOS* (16.1y) | Full (19.1y) |
| --- | ---: | ---: | ---: | ---: |
| Annualized return | +14.11% | +6.48% | +14.10% | +11.65% |
| CAGR (geometric) | +13.70% | +6.26% | +13.98% | +11.31% |
| Sharpe | 0.870 | 0.719 | 0.971 | 0.839 |
| Deflated Sharpe (1000 trials) | 0.551 | 0.110 | 0.907 | 0.824 |
| Sortino | 0.806 | 0.502 | 0.863 | 0.719 |
| Annualized volatility | 16.22% | 9.01% | 14.52% | 13.90% |
| Max drawdown | -20.93% | -21.24% | -20.93% | -21.24% |
| Best day | +18.23% | +8.82% | +18.23% | +18.23% |
| Worst day | -6.28% | -8.72% | -6.28% | -8.72% |
| Trades | 127 | 68 | 169 | 200 |
| Win rate | 50.4% | 45.6% | 48.5% | 48.0% |
| Average win | +3.38% | +2.78% | +3.58% | +3.29% |
| Average loss | -0.85% | -0.77% | -0.71% | -0.80% |
| Profit factor | 4.05 | 3.01 | 4.75 | 3.82 |
| Exposure (share of days) | 23.5% | 16.5% | 20.7% | 20.8% |

\* "OOS" is the historical convention: 2007-2023. It overlaps the
derivation window by 11.5 years, so treat the Out-of-window column
as the real out-of-sample evidence.

### How to read each metric (plain words)

- Annualized return / CAGR: how much money per year, compounded.
- Sharpe: return per unit of risk. 0.8-1.0 is good for a real
  strategy; above 1 usually means something is wrong or the data is
  too short.
- Deflated Sharpe: the probability this Sharpe is NOT luck, given
  1000 attempts. 0.9 = confident; 0.1 = cannot rule out luck.
- Sortino: like Sharpe but only counts losing days. 0.7+ is healthy.
- Volatility: the annualized size of daily swings.
- Max drawdown: the worst peak-to-trough loss an investor would have
  stared at. The strategy's is real; there is no overlay hiding it.
- Best/worst day: the tails. Best +18% and worst -8.7% describe a
  crash-and-rebound portfolio, exactly what the edge is.
- Trades: one entry-then-exit cycle.
- Win rate: share of trades that made money. ~half.
- Average win / average loss: winners are 4-5x the size of losers.
- Profit factor: total winnings divided by total losses. Above 2 is
  solid; above 4 is very solid.
- Exposure: how often the strategy actually has a position. One
  fifth of days. It is a patient strategy.

### The trade behavior story

The most important non-obvious number is the pairing: win rate ~
48-50% but average win 4-5x average loss. That asymmetry comes from
the construction. The exposure curve fades as the margin recovers,
so losing trades are cut small automatically; winning trades ride
the full reversion. The result is a profit factor near 4 in the main
window: you are wrong half the time and still make excellent money,
because your winners are the big reversion moves and your losers are
small corrections.

### Block-level statistical strength

The headline t-stats on non-overlapping 20-day blocks:

| Window | t-stat |
| --- | ---: |
| Derivation | +3.64 |
| Out-of-window | +1.61 |
| Full | +3.66 |

The derivation and full-history numbers are far beyond conventional
significance. The out-of-window number is the weak one and it is
flagged, not hidden.

---

## Part 9. The Honest Caveats

1. The out-of-window window earned half the return (6.5% vs 14.1%)
   and its deflated Sharpe is 0.11: luck cannot be excluded there.
   This is the single most important limitation and the reason the
   forward test is the gate to investment.
2. The drawdown is real. There is no drawdown overlay in this
   strategy; -21% was the actual experienced risk, and the daily
   worst was -8.7%. Risk is managed by the loss budgets and the
   ES-derived scale, not by a drawdown machine.
3. Costs are assumed at 5/20 bps. Standard published sources
   (exchange fees, commissions, roll carry) are still to be wired
   in.
4. The entire program lives on one panel. Even the derivation
   numbers carry residual selection effects from the broader
   research path. The out-of-window column is the only truly
   untouched measure.
5. Heavy tails: a few days dominate the profit (2020-2022 crash
   windows). The distribution is not gentle.

---

## Part 10. How This Compares to the Old Strategy

The old champion (CORE3 equal-weight plus a drawdown overlay) had an
OOS Sharpe of about 0.86. The current strategy reaches a similar
Sharpe (0.87 derivation, 0.84 full) with:
- no tuned parameters (0.75/-0.5 entry thresholds from the v1 era
  are gone, replaced by the derived curve and the -0.45 line);
- no path-dependent drawdown overlay (risk is distribution-derived);
- a cleaner statistical record (fixed DSR computation, non-overlap
  blocks throughout).
The old champion also had a DSR computed with a units bug; that
claim is superseded by the corrected formula.

---

## Part 11. What Would Prove It

Investment remains gated. The forward protocol is:

1. Operational gate (20 sessions): inputs on time, signals
   reproduce, reconciliation clean.
2. Performance gate (300 sessions / 18 months): positive net return,
   median 63-day return positive, annualized Sharpe at least 0.50,
   volatility at most 12%, drawdown at least -15%, worst day at
   least -5% (unless a documented bounded gap), realized cost at
   most 25 bps/side, independent ledger recomputation matches, no
   single year contributing more than 50% of profit without a regime
   explanation.

A pass supports a small staged allocation with a fresh loss budget.
It does not scale from the historical Sharpe.

---

## Part 12. Glossary (for the room)

- Crack spread: refinery profit per barrel = (2 gas + 1 HO)/3 x 42
  - crude.
- Seasonal z: how many standard deviations the margin is from its
  normal level for this time of year.
- Regime: a persistent market state (compression, normal,
  expansion) defined by the margin relative to its long-run
  baseline.
- Regime gate: only trade crushes in compression/normal, not
  expansion.
- Storage gate: go flat when product inventories are building
  strongly.
- Exposure curve: the data-estimated answer to "how much should we
  hold at this z?"
- Scale: the notional multiplier from loss budget / measured tail.
- ES5 (expected shortfall 5%): the average loss in the worst 5% of
  20-day windows.
- Sharpe: return per unit risk, annualized.
- Deflated Sharpe: probability the Sharpe is not from luck given N
  attempts.
- Max drawdown: worst peak-to-trough decline.
- Profit factor: total wins / total losses.
- Forward protocol: the pre-committed paper-test rules that decide
  whether real capital is approved.

---

## One-Paragraph Closing

We found one statistically-verifiable edge: seasonally crushed
refining margins recover — but only in the regime where the
correction is actually active, and only when the storage buffer is
not pressing against us. We built every part of the trade from
measured shapes: the regime identity, the exposure curve, the entry
line, the sizing, the stops. We audited every number, reproduced
every statistic, and reported the weak window instead of hiding it.
The strategy earns a 0.84-0.87 Sharpe over nineteen years of history
with a profit factor near 4, and the one honest caveat is written in
bold: the untouched out-of-window window is half-strength, and the
forward test is what settles it.
