"""Render a composite record's legs + combined backtest into a markdown
writeup, following the same structure as the single-instrument writeup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from algoterminal.composite.engine import CompositeBacktestResult
from algoterminal.composite.models import Composite
from algoterminal.composite.storage import CompositeRecord

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "composite_writeup_template.md.txt"


def _legs_section(result: CompositeBacktestResult) -> str:
    lines = ["| Leg | Version | Weight | Sharpe | Max DD | Trades |", "| --- | --- | --- | --- | --- | --- |"]
    for leg in result.legs:
        trades = leg.stats.n_trades if leg.stats.n_trades is not None else "n/a"
        lines.append(
            f"| {leg.slug} | {leg.version} | {leg.weight:.1%} | {leg.stats.sharpe:.2f} | "
            f"{leg.stats.max_drawdown:.2%} | {trades} |"
        )
    return "\n".join(lines)


def generate_composite_writeup(
    record: CompositeRecord,
    composite: Composite,
    result: CompositeBacktestResult,
) -> str:
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    stats = result.stats

    content = template.format(
        title=composite.title,
        slug=record.slug,
        version=record.version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        thesis=composite.thesis or "None recorded.",
        weighting=composite.weighting,
        legs_section=_legs_section(result),
        cagr=f"{stats.cagr:.2%}",
        sharpe=f"{stats.sharpe:.2f}",
        sortino=f"{stats.sortino:.2f}",
        max_drawdown=f"{stats.max_drawdown:.2%}",
        total_return=f"{stats.total_return:.2%}",
        total_leg_trades=result.total_leg_trades,
    )
    record.writeup_path.write_text(content, encoding="utf-8")
    return content
