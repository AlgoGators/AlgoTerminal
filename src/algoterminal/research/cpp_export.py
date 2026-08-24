"""Generates a C++ trade-engine stub alongside every strategy.py.

The stub mirrors strategy.py's three required functions (generate_signals /
size_positions / apply_risk_rules) as method signatures on a C++ class, with
TODO bodies -- it's a scaffold to port the Python logic into, not an
automatic translation of it, since there's no reference trade-engine
interface in this repo to target. It's derived from the hypothesis (title,
thesis, universe), not from the Python source, so it's cheap to regenerate
every time strategy.py is (re)written.

Written to <record>/TradeEngineImplementation/<ClassName>.{hpp,cpp} -- kept
separate from strategy.py so the pair of files that go into the trade engine
is unambiguous.
"""

from __future__ import annotations

import re
from pathlib import Path

from algoterminal.research.models import Hypothesis
from algoterminal.research.storage import ResearchRecord

_HPP_TEMPLATE = """\
#pragma once
// Auto-generated trade-engine stub for "{title}" ({slug}/{version}).
// Mirrors strategy.py's generate_signals / size_positions / apply_risk_rules.
// This is a scaffold, not a translation -- port the Python logic into the
// TODO bodies in {class_name}.cpp, then swap the double vectors below for
// the real engine's order/position/risk types before wiring this in.
//
// Thesis: {thesis}
// Universe: {universe} ({symbols})
// Expected edge: {expected_edge}

#include <vector>

namespace algogators {{

class {class_name} {{
public:
    {class_name}() = default;

    // Mirrors generate_signals(prices: pd.Series) -> pd.Series
    std::vector<double> generate_signals(const std::vector<double>& prices);

    // Mirrors size_positions(signals: pd.Series) -> pd.Series
    std::vector<double> size_positions(const std::vector<double>& signals);

    // Mirrors apply_risk_rules(positions: pd.Series) -> pd.Series
    std::vector<double> apply_risk_rules(const std::vector<double>& positions);
}};

}}  // namespace algogators
"""

_CPP_TEMPLATE = """\
#include "{class_name}.hpp"

namespace algogators {{

std::vector<double> {class_name}::generate_signals(const std::vector<double>& prices) {{
    // TODO: port the logic from generate_signals() in strategy.py.
    return std::vector<double>(prices.size(), 0.0);
}}

std::vector<double> {class_name}::size_positions(const std::vector<double>& signals) {{
    // TODO: port the logic from size_positions() in strategy.py.
    return std::vector<double>(signals.size(), 0.0);
}}

std::vector<double> {class_name}::apply_risk_rules(const std::vector<double>& positions) {{
    // TODO: port the logic from apply_risk_rules() in strategy.py.
    return positions;
}}

}}  // namespace algogators
"""


def class_name_for_slug(slug: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", slug) if p]
    base = "".join(p.capitalize() for p in parts)
    return f"{base}Strategy" if base else "Strategy"


def export_cpp_stub(record: ResearchRecord, hypothesis: Hypothesis) -> tuple[Path, Path]:
    """Write/refresh the C++ trade-engine stub for `record`. Returns (hpp_path, cpp_path)."""
    class_name = class_name_for_slug(record.slug)
    ctx = dict(
        class_name=class_name,
        title=hypothesis.title,
        thesis=hypothesis.thesis,
        universe=hypothesis.universe,
        symbols=", ".join(hypothesis.symbols),
        expected_edge=hypothesis.expected_edge,
        slug=record.slug,
        version=record.version,
    )
    out_dir = record.path / "TradeEngineImplementation"
    out_dir.mkdir(parents=True, exist_ok=True)
    hpp_path = out_dir / f"{class_name}.hpp"
    cpp_path = out_dir / f"{class_name}.cpp"
    hpp_path.write_text(_HPP_TEMPLATE.format(**ctx), encoding="utf-8")
    cpp_path.write_text(_CPP_TEMPLATE.format(**ctx), encoding="utf-8")
    return hpp_path, cpp_path
