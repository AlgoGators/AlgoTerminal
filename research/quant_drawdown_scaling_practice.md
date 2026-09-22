> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Quant practice: comparing drawdown across different exposure/leverage levels

Date: 2026-09-16
Question: our backtest returns are "% of total account"; the deployment dial
(max position as fraction of account) changes MaxDD% (unit: -35%, 33%
deployment: -11.6%) while Sharpe stays 0.76. Raw MaxDD% across deployments
is not comparable (partial book = cash buffer). What is the accepted practice
for comparing drawdown/risk between strategies at different exposure levels?

## Answer (confirmed practice)

Practitioners do not compare raw MaxDD% across strategies with different
leverage. They use one or more of:

1. Sharpe / Sortino / Information Ratio — scale-free by construction (ratio of
   return to risk; both scale together). Default cross-strategy metric.
2. Volatility targeting — re-scale EVERY strategy to a common ex-ante
   volatility (10% annualized is a common convention) before comparing any
   level metric including MaxDD%. This equalizes exposure, so MaxDD% becomes
   comparable. The dominant institutional practice (managed-vol funds,
   Schroders strategic portfolios with stated vol targets, CalPERS reporting
   templates, AQR "actively manage volatility").
3. Calmar / MAR ratio (CAGR / MaxDD) — the drawdown-adjusted return ratio.
   First-order invariant to uniform scaling: leverage multiplies the
   numerator and denominator by the same factor, so the ratio survives.
   Caveat: only approximately — costs, funding, and leverage-related path
   effects break exactness; CAGR/MaxDD peaks just below Kelly leverage.
4. Per-unit-risk normalization — divide level metrics by exposure or by
   realized volatility (DD/vol, return/vol). Outcast Beta result: the best
   predictor of drawdown risk is portfolio vol / Sharpe, i.e., the fraction
   of full Kelly allocation — drawdown is set by how far you scale toward Kelly.
5. Duration-aware drawdown measures — AQR "Portfolio Protection: It's a
   Long-Term Story": depth AND length of drawdown matter; academic stream via
   Chekhlov-Uryasev-Zabarankin conditional drawdown-at-risk (CDaR) and
   Grossman-Zhou 1993 (drawdown as an explicit constraint, W >= alpha*M,
   with the alpha as an exogenous risk budget; control is exercised through
   exposure choice).

## Findings by sub-question

1. Vol-targeting as comparison standard
   - Moreira & Muir (2017): vol-managed portfolios raise Sharpe; Harvey,
     Hoyle, Korgaonkar, Rattray, Sargaison, Van Hemert (2018): vol targeting
     reduces tail risk; implementation practice: "sizes a position inversely
     to a forecast of its volatility".
     - https://repub.eur.nl/pub/130215/Bongaerts-Kang-van-Dijk-Conditional-volatility-targeting-2020-FAJ.pdf
     - https://quantdecoded.com/en/volatility-targeting-scaling-risk-for-better-returns
   - Institutional reporting at stated vol targets: Schroders strategic index
     portfolios (vol ranges vs MSCI), CalPERS ALM reporting (vol as a stated
     target metric), LSV / Acadian / State Street managed-vol funds.
     - https://api.schroders.com/document-store/SFWFR-Schroder-Strategic-Index-Portfolio-10-FMR-UKEN.pdf
     - https://www.calpers.ca.gov/documents/202507-full-day-1-1-2-presentation-asset-liability-management-further-discussion-a/download?inline=
     - https://www.lsvasset.com/pdf/fund-docs/LSVMX-TSR-10.31.25.pdf
   - AQR guidance: "actively manage volatility" as one of five tail-risk
     responses.
     - https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/AQR-Chasing-Your-Own-Tail-Risk.pdf

2. Calmar ratio and leverage invariance
   - Direct practice statement: "Calmar barely moves when you add leverage.
     Leverage multiplies your return and your drawdown by roughly the same
     factor. The ratio survives. What changes is the size of both numbers —
     and size is a question about your stomach, your broker, and your funding
     cost, not about the model."
     - https://reflectionsofreality.substack.com/p/i-can-show-you-the-stars-all-you
   - Definition and caveats: "Not comparable across return frequencies or
     leverage without care — scaling leverage scales both numerator and
     (roughly) denominator"; some houses use 36-month trailing, others full
     history (MAR).
     - https://www.submillisecond.com/glossary/returns/calmar-ratio
     - https://www.ecassets.com/learn/calmar-ratio
     - https://www.getswoopr.com/risk-management/performance/calmar-ratio/
   - The exactness caveat: CAGR/MaxDD peaks just below full Kelly leverage —
     beyond that, funding costs and ruin effects bend the ratio.
     - https://vincentmayeski.substack.com/p/cagrmaxdd-peaks-just-below-kelly

3. Allocator comparison practice
   - QuantOracle comparison of Sharpe vs Sortino vs Calmar and which allocators
     use: Sharpe = default across funds; Sortino = asymmetric strategies;
     Calmar = capital allocation, risk-of-ruin, "surviving real drawdowns".
     - https://quantoracle.dev/compare/sharpe-vs-sortino-vs-calmar
   - Multi-strategy hedge fund analysis (Frontier Advisors): risk-adjusted
     comparisons and capital allocation across sub-strategies.
     - https://www.frontieradvisors.com.au/wp-content/uploads/2023/08/Frontier-Line-211-A-comprehensive-analysis-of-the-costs-and-benefits-of-multi-strategy-hedge-funds.pdf

4. Academic drawdown literature
   - Grossman & Zhou (1993), "Optimal Investment Strategies for Controlling
     Drawdowns", Mathematical Finance 3(3): drawdown as an explicit
     constraint (wealth must never fall below alpha x running maximum);
     control via portfolio/exposure choice. Alpha is an exogenous risk
     parameter — consistent with our finding that the "cap" is a constraint,
     not a strategy parameter.
     - https://doi.org/10.1111/j.1467-9965.1993.tb00044.x
   - Chekhlov-Uryasev-Zabarankin CDaR stream and V2 ratio (drawdown magnitude
     and duration/volatility of drawdowns).
     - https://www.foliolab.ai/docs/metrics/v2-ratio

5. Normalized drawdown measures
   - "Drawdown risk = portfolio volatility normalized (divided) by Sharpe
     ratio, i.e. fraction of full Kelly allocation": DD risk is a function of
     how far you scale toward Kelly.
     - https://outcastbeta.com/drawdown-risk-portfolio-volatility-normalized-by-sharpe-ratio/
   - CME: portfolio management with drawdown-based measures.
     - https://www.cmegroup.com/

## Application to our crack-spread strategy

Unit-risk series (scale 1.0, tail-stop + cooldown 3, walk-forward 2012-2026):
annualized vol = 30.65%. Vol-targeted to 10% annualized (factor 0.326):

- CAGR +7.27%, MaxDD -12.44%, Sharpe 0.751, Calmar 0.58
- 2019+ fully-clean slice: MaxDD -8.99%, Sharpe 0.864

Note: the 10%-vol factor (0.326) lands almost exactly at the Kelly-half
multiple, a consistency check that "Kelly-half" was effectively a 10%-vol
book.

## Direct answer to the captain's question

"Do we just compare relative to the actual exposed?" — Yes; that is the
per-unit-risk route: divide level metrics (return, drawdown) by exposure or
by realized volatility before comparing. Equivalently: normalize every
strategy to one vol target (10% is conventional) and then compare MaxDD%
directly; or use exposure-invariant ratios (Calmar, Sortino, Sharpe). Raw
MaxDD% from differently-deployed runs is not comparable because the
uninvested cash buffer damps the account-level number.

## Gaps / verification notes

- The "Calmar is leverage-invariant" claim is corroborated by practice
  sources (glossary + practitioner substack) but is not stated as a formal
  theorem in the sources found; the exact statement requires zero costs and
  linear scaling (our trailing-stop/costs make it approximate — confirmed by
  our own numbers: damage per risked dollar 0.34-0.37 across modes).
- Grossman-Zhou confirmed via Wiley/EconPapers abstract; full text is
  paywalled, only the abstract and structure were used.
- Vol-targeting evidence (Moreira-Muir, Harvey et al.) is real but focuses on
  Sharpe gains; the "report at 10% vol for comparability" convention is
  inferred from fund docs (Schroders, managed-vol funds) and allocator
  templates (CalPERS), not from one canonical citation.
