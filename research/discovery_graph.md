> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Discovery graph (graphify auto-build)

Auto-discovery layer over the curated truth graph. Built on
`research/` and `findings/` plus code, via the graphify pipeline.

## Outputs (generated, gitignored)

- `discovery/graphify-out/graph.html` — interactive graph, open in browser.
- `discovery/graphify-out/GRAPH_REPORT.md` — god nodes, surprising connections,
  suggested questions.
- `discovery/graphify-out/graph.json` — raw graph data.
- `discovery/graphify-out/manifest.json` — incremental update manifest.

## Rebuild

```
discovery/graphify-out/.graphify_python ... (venv at /home/sebas/.local/venvs/graphify)
graphify export html          # after semantic/AST extraction
```

First build used host-agent semantic extraction (30 docs, 2 chunks)
because the child model provider is unavailable to subagents in this
environment. No Gemni key was needed.

## Purpose and rule

The discovery graph surfaces connections we have not curated. A
surprise is a suggestion, not a fact. Promotion rule: any surprise
that looks promising goes through a Tier 1 phenomenon test, then
becomes a curated edge in `research/graph/edges.csv` with an honest
evidence tag. The curated graph remains the truth layer.

## First-build highlights

God nodes are dominated by the vendored algoterminal code
(AssetClass, ResearchRecord). The doc-level nodes are the strategy
corpus. Surprising connections confirmed framework links: crisis
reversion edge to champion, flow-driven-not-physical to champion,
seasonal-z-is-the-signal to champion.

Community labels: Cointegration analytics, Custom agents, Chart
rendering, Signal scoring, Data store, Providers, App context, CLI
commands, Console stages, Backtest returns, Instrument metadata,
v2x overlay engine.

## Queries

`graphify query "<question>"` from the worktree root answers against
this graph. Use it for cross-document discovery; use
`python graph_web.py <cmd>` for the curated truth layer.
