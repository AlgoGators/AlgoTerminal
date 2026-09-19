"""Deterministic capability probe for a QuantConnect LEAN fixture."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Callable

which: Callable[[str], str | None] = shutil.which


@dataclass(frozen=True)
class CapabilityResult:
    status: str
    missing: tuple[str, ...]

    def render(self) -> str:
        missing = ", ".join(self.missing) or "none"
        return f"status={self.status}; missing={missing}"


def _quantconnect_lean_cli() -> bool:
    """Return true only for the QuantConnect CLI, not the Lean theorem prover."""
    for command in ("lean", "lean-cli"):
        executable = which(command)
        if executable is None:
            continue
        try:
            output = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if "quantconnect" in output.lower() or "lean cli" in output.lower():
            return True
    return False


def probe_capabilities(fixture_path: str | Path) -> CapabilityResult:
    """Check the runtime, CLI, and local data needed by a full LEAN fixture."""
    missing: list[str] = []
    if which("dotnet") is None:
        missing.append("dotnet runtime")
    if not _quantconnect_lean_cli():
        missing.append("QuantConnect LEAN CLI")
    if not Path(fixture_path).is_dir():
        missing.append("LEAN fixture data")
    status = "valid" if not missing else "unavailable"
    return CapabilityResult(status, tuple(missing))


if __name__ == "__main__":
    print(probe_capabilities(Path(__file__).with_name("lean_fixture")).render())
