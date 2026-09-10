"""Modal form for creating a new composite strategy from other saved strategies."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

from algoterminal.composite.models import WEIGHTINGS, Composite
from algoterminal.composite.storage import CompositeRecord, create_composite


class CompositeModal(ModalScreen[CompositeRecord | None]):
    """Create a new composite: a title, 2+ leg nicknames, and a weighting."""

    DEFAULT_CSS = """
    CompositeModal {
        align: center middle;
    }
    #composite-form {
        width: 76;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    #composite-form Label {
        margin-top: 1;
    }
    #composite-hint {
        color: $text-muted;
    }
    #composite-buttons {
        margin-top: 1;
        height: auto;
        align: right middle;
    }
    """

    def __init__(self, available_slugs: list[str]) -> None:
        super().__init__()
        self._available_slugs = available_slugs

    def compose(self) -> ComposeResult:
        with Vertical(id="composite-form"):
            yield Label("[bold]New Cumulative Strategy[/bold]")
            yield Label("Title")
            yield Input(placeholder="e.g. WTI Crack Spread Book", id="title")
            yield Label("Legs (comma-separated saved strategy nicknames, 2+)")
            yield Input(placeholder=", ".join(self._available_slugs[:3]) or "no saved strategies yet", id="legs")
            yield Label(f"Available: {', '.join(self._available_slugs) or '(none saved yet)'}", id="composite-hint")
            yield Label("Weighting")
            yield Select([(w, w) for w in WEIGHTINGS], value="inverse_vol", id="weighting")
            yield Label("Thesis (optional)")
            yield Input(placeholder="Why combine these legs?", id="thesis")
            with Grid(id="composite-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return

        title = self.query_one("#title", Input).value.strip()
        legs_raw = self.query_one("#legs", Input).value.strip()
        weighting = self.query_one("#weighting", Select).value
        thesis = self.query_one("#thesis", Input).value.strip()
        legs = [s.strip() for s in legs_raw.split(",") if s.strip()]

        if not title:
            self.notify("Title is required.", severity="error")
            return
        if len(legs) < 2:
            self.notify("Need at least 2 legs (comma-separated nicknames).", severity="error")
            return
        unknown = [s for s in legs if s not in self._available_slugs]
        if unknown:
            self.notify(f"Unknown nickname(s): {', '.join(unknown)}", severity="error")
            return

        composite = Composite(title=title, legs=legs, thesis=thesis, weighting=weighting)
        record = create_composite(composite)
        self.dismiss(record)
