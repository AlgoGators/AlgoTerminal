"""The structured Composite object: a named strategy built by combining other
saved research records' own backtest results -- not a new strategy.py, not
new data. See `algoterminal.composite.engine` for how the legs are combined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from algoterminal.research.models import slugify

WEIGHTINGS = ("inverse_vol", "equal")


@dataclass
class Composite:
    title: str
    legs: list[str]  # research-record nicknames; each resolves to its own latest backtested version
    thesis: str = ""
    weighting: str = "inverse_vol"  # "inverse_vol" (equalize each leg's risk contribution) or "equal"
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def slug(self) -> str:
        return slugify(self.title)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "legs": self.legs,
            "thesis": self.thesis,
            "weighting": self.weighting,
            "author": self.author,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Composite":
        return cls(
            title=data["title"],
            legs=list(data["legs"]),
            thesis=data.get("thesis", ""),
            weighting=data.get("weighting", "inverse_vol"),
            author=data.get("author", ""),
            created_at=data.get("created_at", ""),
        )
