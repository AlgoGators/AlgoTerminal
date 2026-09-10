"""Typer CLI entry point.

Running `algoterminal` with no subcommand launches the full-screen TUI.
Subcommands exist for scripting individual research-cycle stages and
comparison tools without leaving the shell.
"""

from __future__ import annotations

from typing import Optional

import typer

from algoterminal.config import ensure_dirs
from algoterminal.console import console

app = typer.Typer(
    name="algoterminal",
    help="AlgoTerminal — a terminal research workbench for the AlgoGators Quantitative Research team.",
    no_args_is_help=False,
)
universe_app = typer.Typer(help="Manage named instrument baskets (universes).")
compare_app = typer.Typer(help="Cross-asset comparison tools.")
cache_app = typer.Typer(help="Manage the local data cache.")
composite_app = typer.Typer(help="Composite strategies built by combining other saved strategies.")
app.add_typer(universe_app, name="universe")
app.add_typer(compare_app, name="compare")
app.add_typer(cache_app, name="cache")
app.add_typer(composite_app, name="composite")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    ensure_dirs()
    if ctx.invoked_subcommand is None:
        from algoterminal.tui.app import run as run_tui

        run_tui()


@app.command()
def tui() -> None:
    """Launch the full-screen terminal UI explicitly."""
    from algoterminal.tui.app import run as run_tui

    run_tui()


@app.command()
def hypothesis() -> None:
    """Run the interactive hypothesis wizard and save a new research record."""
    from algoterminal.research.hypothesis import run_hypothesis_wizard

    run_hypothesis_wizard(console)


def _resolve_record(slug: str, version: Optional[str]):
    from algoterminal.research.storage import get_record, latest_record

    record = get_record(slug, version) if version else latest_record(slug)
    if record is None:
        console.print(f"[error]No research record found for nickname {slug!r}.[/error]")
        raise typer.Exit(code=1)
    return record


@app.command()
def data(slug: str, version: Optional[str] = typer.Option(None, help="Specific record version; defaults to latest")) -> None:
    """Pull and validate data for a saved hypothesis."""
    from algoterminal.data import provider_for_source
    from algoterminal.research.data_stage import pull_and_validate, save_quality_reports

    record = _resolve_record(slug, version)
    hyp = record.load_hypothesis()
    _, reports = pull_and_validate(hyp, provider_for_source(hyp.source))
    save_quality_reports(record, reports)

    for r in reports:
        status = "[success]OK[/success]" if r.ok else f"[warning]{'; '.join(r.issues)}[/warning]"
        console.print(f"{r.symbol}: {r.rows} rows, {r.start} -> {r.end} — {status}")


@app.command()
def backtest(slug: str, version: Optional[str] = typer.Option(None, help="Specific record version; defaults to latest")) -> None:
    """Scaffold (if needed) and run the backtest for a saved hypothesis."""
    from algoterminal.data import provider_for_source
    from algoterminal.research.backtest import run_backtest, save_backtest_result
    from algoterminal.research.data_stage import pull_and_validate, save_quality_reports
    from algoterminal.research.methodology import load_strategy_module, scaffold_strategy
    from algoterminal.tui.widgets.stats_table import build_stats_table

    record = _resolve_record(slug, version)
    hyp = record.load_hypothesis()

    provider_data, reports = pull_and_validate(hyp, provider_for_source(hyp.source))
    save_quality_reports(record, reports)

    primary = hyp.symbols[0]
    if primary not in provider_data or provider_data[primary].empty:
        console.print(f"[error]No data for primary symbol {primary}.[/error]")
        raise typer.Exit(code=1)

    if not record.strategy_path.exists():
        scaffold_strategy(record, hyp)
        console.print(f"Scaffolded strategy: {record.strategy_path}")

    strategy = load_strategy_module(record.strategy_path)
    result = run_backtest(strategy, provider_data[primary]["close"], is_level=hyp.source == "derived")
    save_backtest_result(record, result)

    console.print(build_stats_table(result.stats, title=f"{hyp.title} — Backtest"))


@app.command()
def writeup(slug: str, version: Optional[str] = typer.Option(None, help="Specific record version; defaults to latest")) -> None:
    """Generate the markdown research writeup for a saved, backtested hypothesis."""
    from algoterminal.research.backtest import has_backtest_result, load_backtest_result
    from algoterminal.research.data_stage import load_quality_reports
    from algoterminal.research.writeup import generate_writeup

    record = _resolve_record(slug, version)
    if not has_backtest_result(record):
        console.print("[error]Run `algoterminal backtest` before generating a writeup.[/error]")
        raise typer.Exit(code=1)

    hyp = record.load_hypothesis()
    reports = load_quality_reports(record)
    result = load_backtest_result(record)
    generate_writeup(record, hyp, reports, result)
    console.print(f"[success]Writeup written to {record.writeup_path}[/success]")


def _resolve_composite_record(slug: str, version: Optional[str]):
    from algoterminal.composite.storage import get_composite_record, latest_composite_record

    record = get_composite_record(slug, version) if version else latest_composite_record(slug)
    if record is None:
        console.print(f"[error]No composite strategy found for nickname {slug!r}.[/error]")
        raise typer.Exit(code=1)
    return record


@composite_app.command("create")
def composite_create(
    title: str,
    legs: str = typer.Option(..., help="Comma-separated nicknames of existing saved strategies to combine"),
    weighting: str = typer.Option("inverse_vol", help="'inverse_vol' (equalize risk contribution) or 'equal'"),
    thesis: str = typer.Option("", help="Optional note on why these legs are combined"),
) -> None:
    """Create a new composite strategy from other saved strategies' nicknames."""
    from algoterminal.composite.models import WEIGHTINGS, Composite
    from algoterminal.composite.storage import create_composite

    leg_list = [s.strip() for s in legs.split(",") if s.strip()]
    if len(leg_list) < 2:
        console.print("[error]Need at least 2 legs (comma-separated nicknames).[/error]")
        raise typer.Exit(code=1)
    if weighting not in WEIGHTINGS:
        console.print(f"[error]weighting must be one of {WEIGHTINGS}.[/error]")
        raise typer.Exit(code=1)

    composite = Composite(title=title, legs=leg_list, thesis=thesis, weighting=weighting)
    record = create_composite(composite)
    console.print(f"[success]Saved composite {record.slug}/{record.version}[/success] ({', '.join(leg_list)})")


@composite_app.command("backtest")
def composite_backtest(
    slug: str, version: Optional[str] = typer.Option(None, help="Specific record version; defaults to latest")
) -> None:
    """Combine each leg's own saved backtest into the composite's backtest."""
    from algoterminal.composite.engine import CompositeError, run_composite_backtest, save_composite_backtest
    from algoterminal.tui.widgets.stats_table import build_stats_table

    record = _resolve_composite_record(slug, version)
    composite = record.load_composite()

    try:
        result = run_composite_backtest(composite.legs, composite.weighting)
    except CompositeError as exc:
        console.print(f"[error]{exc}[/error]")
        raise typer.Exit(code=1)

    save_composite_backtest(record, result)
    console.print(build_stats_table(result.stats, title=f"{composite.title} — Combined Backtest"))
    for leg in result.legs:
        console.print(f"  {leg.slug}/{leg.version}: weight {leg.weight:.1%}, Sharpe {leg.stats.sharpe:.2f}")


@composite_app.command("writeup")
def composite_writeup(
    slug: str, version: Optional[str] = typer.Option(None, help="Specific record version; defaults to latest")
) -> None:
    """Generate the markdown writeup for a backtested composite."""
    from algoterminal.composite.engine import has_composite_backtest, load_composite_backtest
    from algoterminal.composite.writeup import generate_composite_writeup

    record = _resolve_composite_record(slug, version)
    if not has_composite_backtest(record):
        console.print("[error]Run `algoterminal composite backtest` before generating a writeup.[/error]")
        raise typer.Exit(code=1)

    composite = record.load_composite()
    result = load_composite_backtest(record)
    generate_composite_writeup(record, composite, result)
    console.print(f"[success]Writeup written to {record.writeup_path}[/success]")


@composite_app.command("list")
def composite_list() -> None:
    """List saved composite strategies."""
    from algoterminal.composite.storage import list_composite_slugs, list_composite_versions

    for slug in list_composite_slugs():
        versions = list_composite_versions(slug)
        if not versions:
            continue
        latest = versions[-1]
        composite = latest.load_composite()
        console.print(f"[brand]{slug}[/brand] ({latest.version}): {', '.join(composite.legs)} [{composite.weighting}]")


@universe_app.command("list")
def universe_list() -> None:
    """List saved universes."""
    from algoterminal.data.universe import UniverseStore

    for u in UniverseStore().list():
        console.print(f"[brand]{u.name}[/brand] ({u.asset_class.value}): {', '.join(u.symbols)}")


@universe_app.command("show")
def universe_show(name: str) -> None:
    """Show one universe's members."""
    from algoterminal.data.universe import UniverseStore

    u = UniverseStore().load(name)
    console.print(f"[brand]{u.name}[/brand] — {u.description}")
    console.print(f"Asset class: {u.asset_class.value}")
    console.print(f"Symbols: {', '.join(u.symbols)}")


@universe_app.command("create")
def universe_create(
    name: str,
    symbols: str = typer.Option(..., help="Comma-separated symbols"),
    asset_class: str = typer.Option("equity", help="equity | future | fx | crypto | custom"),
    description: str = typer.Option("", help="Optional description"),
) -> None:
    """Save a new named universe."""
    from algoterminal.data.provider import AssetClass
    from algoterminal.data.universe import Universe, UniverseStore

    u = Universe(
        name=name,
        asset_class=AssetClass(asset_class),
        symbols=[s.strip() for s in symbols.split(",") if s.strip()],
        description=description,
    )
    UniverseStore().save(u)
    console.print(f"[success]Saved universe {name!r}.[/success]")


@universe_app.command("delete")
def universe_delete(name: str) -> None:
    """Delete a saved universe."""
    from algoterminal.data.universe import UniverseStore

    UniverseStore().delete(name)
    console.print(f"[success]Deleted universe {name!r}.[/success]")


@universe_app.command("add-symbol")
def universe_add_symbol(name: str, symbol: str) -> None:
    """Add a symbol to an existing universe."""
    from algoterminal.data.universe import UniverseStore

    store = UniverseStore()
    u = store.load(name)
    if symbol not in u.symbols:
        u.symbols.append(symbol)
        store.save(u)
    console.print(f"[success]{name}[/success]: {', '.join(u.symbols)}")


@universe_app.command("remove-symbol")
def universe_remove_symbol(name: str, symbol: str) -> None:
    """Remove a symbol from an existing universe."""
    from algoterminal.data.universe import UniverseStore

    store = UniverseStore()
    u = store.load(name)
    u.symbols = [s for s in u.symbols if s != symbol]
    store.save(u)
    console.print(f"[success]{name}[/success]: {', '.join(u.symbols)}")


@cache_app.command("status")
def cache_status() -> None:
    """List everything currently cached locally."""
    from rich.table import Table

    from algoterminal.data import cache

    table = Table(title="[brand]Local Data Cache[/brand]")
    table.add_column("Provider")
    table.add_column("Symbol")
    table.add_column("Rows", justify="right")
    table.add_column("Start")
    table.add_column("End")
    table.add_column("Size (KB)", justify="right")

    entries = cache.list_cached()
    for e in entries:
        table.add_row(e.provider, e.symbol, str(e.rows), str(e.start or "-"), str(e.end or "-"), f"{e.size_bytes / 1024:.1f}")

    console.print(table)
    console.print(f"{len(entries)} cached symbol(s).")


@cache_app.command("clear")
def cache_clear(
    provider: Optional[str] = typer.Option(None, help="Only clear this provider's cache"),
    symbol: Optional[str] = typer.Option(None, help="Only clear this symbol's cache"),
) -> None:
    """Clear the local data cache, optionally filtered by provider and/or symbol."""
    from algoterminal.data import cache

    removed = cache.clear(provider_name=provider, symbol=symbol)
    console.print(f"[success]Removed {removed} cached file(s).[/success]")


def _load_universe_data(universe_or_symbols: str):
    """Fetch a universe's (or comma-separated symbols') data as {symbol: close-price series}."""
    from algoterminal.data.universe import UniverseStore
    from algoterminal.data import default_provider

    store = UniverseStore()
    try:
        universe = store.load(universe_or_symbols)
        symbols, asset_class = universe.symbols, universe.asset_class
    except KeyError:
        from algoterminal.data.provider import AssetClass

        symbols, asset_class = store.resolve(universe_or_symbols), AssetClass.EQUITY

    provider = default_provider()
    data = provider.fetch_many(symbols, asset_class)
    return {sym: df["close"] for sym, df in data.items() if not df.empty}


@compare_app.command("matrix")
def compare_matrix(universe: str) -> None:
    """Correlation matrix across a universe (or comma-separated symbols)."""
    from algoterminal.analytics.correlation import correlation_matrix
    from algoterminal.charts.heatmap import correlation_heatmap

    data = _load_universe_data(universe)
    console.print(correlation_heatmap(correlation_matrix(data)))


@compare_app.command("cointegration")
def compare_cointegration(sym_a: str, sym_b: str) -> None:
    """Engle-Granger cointegration test between two instruments."""
    from algoterminal.analytics.cointegration import engle_granger_test
    from algoterminal.data.provider import AssetClass
    from algoterminal.data import default_provider

    provider = default_provider()
    raw = provider.fetch_many([sym_a, sym_b], AssetClass.EQUITY)
    data = {sym: df["close"] for sym, df in raw.items() if not df.empty}
    result = engle_granger_test(data, sym_a, sym_b)
    console.print(f"t-statistic: {result.t_statistic:.4f}")
    console.print(f"p-value: {result.p_value:.4f}")
    console.print(f"cointegrated (5%): {result.is_cointegrated()}")


@compare_app.command("relative")
def compare_relative(universe: str) -> None:
    """Relative performance chart (rebased to 100) across a universe."""
    from algoterminal.analytics.relative_performance import relative_performance
    from algoterminal.charts.terminal_charts import multi_line_chart

    data = _load_universe_data(universe)
    console.print(multi_line_chart(relative_performance(data), title="Relative Performance"))


if __name__ == "__main__":
    app()
