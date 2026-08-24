"""Exports the internal scripts that define how AlgoTerminal builds the
prompt it feeds to Claude/Codex (or a registered custom agent) every time a
strategy is edited from the Design tab.

This is for wiring the same prompt-building logic into your own off-path
terminal agent -- one that runs from a plain terminal instead of through
this TUI -- so it edits strategy.py under the same contract (required
function names, single-file scope, etc.) that AlgoTerminal itself enforces.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

_THIS_DIR = Path(__file__).parent
_TEMPLATE_PATH = _THIS_DIR / "templates" / "strategy_template.py.txt"

_README = """\
# AlgoTerminal strategy-building scripts

These are the exact scripts AlgoTerminal uses to build every strategy.py it
generates and every prompt it sends to Claude/Codex (or a custom agent) when
editing one from the Design tab. Use them to build your own off-path agent
that edits strategy.py files under the same contract this app enforces.

## Contents

- `design_agent.py` -- `build_prompt()` is the prompt template sent to the
  coding agent. `REQUIRED_FUNCTIONS` is the contract every strategy.py must
  satisfy: `generate_signals`, `size_positions`, `apply_risk_rules`.
- `methodology.py` -- `scaffold_strategy()` writes the initial strategy.py
  from `templates/strategy_template.py.txt`.
- `templates/strategy_template.py.txt` -- the blank scaffold itself.

## The contract

A strategy.py must define exactly these three top-level functions (renaming,
removing, or changing their signature breaks the backtest engine, which
looks them up via `hasattr`):

  - generate_signals(...)
  - size_positions(...)
  - apply_risk_rules(...)

## Invocation shape

Both `claude -p` and `codex exec` are run scoped to a single research
record's own directory (never the rest of the codebase), with the prompt
passed over stdin (not argv -- argv has platform-specific truncation issues
with multi-line prompts). See `design_agent.py` for the exact subprocess
calls.
"""


def export_prompt_scripts(destination_dir: Path | None = None) -> Path:
    """Bundle the prompt-building scripts into a zip. Returns the zip's path."""
    destination_dir = destination_dir or _default_destination_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    zip_path = destination_dir / "algoterminal-strategy-scripts.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(_THIS_DIR / "design_agent.py", "design_agent.py")
        zf.write(_THIS_DIR / "methodology.py", "methodology.py")
        zf.write(_TEMPLATE_PATH, "templates/strategy_template.py.txt")
        zf.writestr("README.md", _README)
    return zip_path


def _default_destination_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()
