"""Versioned, on-disk storage for composite records -- mirrors
`algoterminal.research.storage`, under its own top-level directory
(~/.algoterminal/composites/<slug>/<version>/) so composites and the
single-instrument strategies they're built from stay clearly separate:

    ~/.algoterminal/composites/
        crack-spread-book/
            20260910-120000/
                composite.yaml
                backtest_results.json
                equity_curve.parquet
                writeup.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from algoterminal.composite.models import Composite
from algoterminal.config import COMPOSITE_DIR, ensure_dirs


@dataclass
class CompositeRecord:
    slug: str
    version: str
    path: Path

    @property
    def composite_path(self) -> Path:
        return self.path / "composite.yaml"

    @property
    def backtest_results_path(self) -> Path:
        return self.path / "backtest_results.json"

    @property
    def equity_curve_path(self) -> Path:
        return self.path / "equity_curve.parquet"

    @property
    def writeup_path(self) -> Path:
        return self.path / "writeup.md"

    def load_composite(self) -> Composite:
        with open(self.composite_path, encoding="utf-8") as f:
            return Composite.from_dict(yaml.safe_load(f))


def create_composite(composite: Composite) -> CompositeRecord:
    """Start a new version of a composite and persist it."""
    ensure_dirs()
    slug = composite.slug
    version = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = COMPOSITE_DIR / slug / version
    path.mkdir(parents=True, exist_ok=True)

    with open(path / "composite.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(composite.to_dict(), f, sort_keys=False)

    return CompositeRecord(slug=slug, version=version, path=path)


def list_composite_slugs() -> list[str]:
    ensure_dirs()
    return sorted(p.name for p in COMPOSITE_DIR.iterdir() if p.is_dir())


def list_composite_versions(slug: str) -> list[CompositeRecord]:
    slug_dir = COMPOSITE_DIR / slug
    if not slug_dir.exists():
        return []
    return [
        CompositeRecord(slug=slug, version=p.name, path=p)
        for p in sorted(slug_dir.iterdir())
        if p.is_dir()
    ]


def latest_composite_record(slug: str) -> CompositeRecord | None:
    versions = list_composite_versions(slug)
    return versions[-1] if versions else None


def get_composite_record(slug: str, version: str) -> CompositeRecord:
    path = COMPOSITE_DIR / slug / version
    if not path.exists():
        raise KeyError(f"no such composite record: {slug}/{version}")
    return CompositeRecord(slug=slug, version=version, path=path)
