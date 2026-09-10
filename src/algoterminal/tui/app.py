"""AlgoTerminal — full-screen Textual application.

Tabs (Strategies / Data Universes / Compare / Design) plus a top launch bar:
type a strategy idea and press Enter to open a pre-filled hypothesis form and
jump straight to Design once it's saved — a faster on-ramp than starting from
a blank "New" form on the Strategies tab.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Input, Static, TabbedContent, TabPane

from algoterminal.config import ensure_dirs
from algoterminal.research.models import Hypothesis
from algoterminal.research.storage import ResearchRecord
from algoterminal.tui.screens.compare_screen import ComparePane
from algoterminal.tui.screens.data_screen import DataPane
from algoterminal.tui.screens.design_screen import DesignPane
from algoterminal.tui.screens.hypothesis_modal import HypothesisModal
from algoterminal.tui.screens.research_screen import ResearchPane
from algoterminal.tui.screens.splash_screen import SplashScreen
from algoterminal.theme import ALGOGATORS_THEME

_TITLE_MAX_LEN = 60


class AlgoTerminalApp(App):
    """AlgoTerminal — the QR team's terminal research workbench."""

    TITLE = "AlgoTerminal"
    SUB_TITLE = "Data Driven, Student Run."

    CSS = """
    #launch-bar {
        dock: top;
        height: 3;
        padding: 0 1;
        background: $panel;
        border-bottom: solid $primary;
    }
    #launch-prompt {
        width: auto;
        color: $primary;
        text-style: bold;
        content-align: left middle;
        padding-right: 1;
    }
    #launch-input {
        border: none;
        background: $panel;
    }
    #records-col {
        width: 45%;
        border-right: solid $primary;
    }
    #detail-col {
        width: 1fr;
        padding: 0 1;
    }
    #record-detail-scroll {
        height: 12;
        border-bottom: solid $primary;
    }
    #charts-tabs {
        height: 1fr;
    }
    #monthly-returns-scroll, #dd-periods-scroll, #compare-output {
        /* These render a Rich Table wider than the pane (13 columns for the
        monthly-returns calendar). Left at the default overflow-x: hidden,
        the table gets squeezed into the pane's width and Rich compresses/
        wraps every cell to fit, which is what made the numbers unreadable.
        Scrolling horizontally instead lets the table keep its natural
        column widths. */
        overflow-x: auto;
    }
    #monthly-returns-table, #dd-periods-table, #compare-table {
        /* Static has no width rule at all by default (only height: auto),
        which makes Textual just fill the container's width instead of
        measuring the renderable's natural size — so the table above was
        being force-rendered at the pane's (narrower) width regardless of
        content, and once the table no longer shrank to fit (see above), the
        overflow just got clipped at the pane's edge instead of scrolling.
        Explicit width: auto makes Textual size the box off the actual
        rendered Rich Table, so the scrollbar has real content to scroll. */
        width: auto;
    }
    #research-buttons, #composite-buttons {
        height: auto;
        padding: 1 0;
    }
    #strategy-kind-tabs {
        height: auto;
    }
    #research-buttons Select {
        width: 22;
        margin-left: 1;
    }
    #research-thinking {
        padding: 0 0 1 0;
    }
    #design-thinking {
        padding: 0 0 1 0;
    }
    #compare-controls {
        height: auto;
        padding: 1;
    }
    #compare-controls Select {
        width: 1fr;
        margin-right: 1;
    }
    #compare-controls #compare-timeframe {
        width: 20;
    }
    #universe-col {
        width: 45%;
        border-right: solid $primary;
    }
    #universe-buttons, #cache-buttons {
        height: auto;
        padding: 1 0;
    }
    #data-detail-col {
        width: 1fr;
        padding: 0 1;
    }
    #universe-detail {
        height: auto;
        padding: 1 0;
    }
    #universes-note {
        height: auto;
        padding: 1;
        border-bottom: solid $primary;
    }
    #design-records-col {
        width: 40%;
        border-right: solid $primary;
    }
    #design-detail {
        height: auto;
        padding: 1 0;
    }
    #design-code-col {
        width: 1fr;
        padding: 0 1;
    }
    #design-prompt-row {
        height: auto;
        padding-top: 1;
    }
    #design-prompt-row Select {
        width: 16;
        margin-right: 1;
    }
    #design-prompt-row Input {
        width: 1fr;
        margin-right: 1;
    }
    #design-agent-row {
        height: auto;
        padding-bottom: 1;
    }
    #design-agent-row Button {
        margin-right: 1;
    }
    #design-status {
        height: auto;
        padding: 0 0 1 0;
    }
    #design-code {
        height: 1fr;
        border: solid $primary;
    }
    #design-code-buttons {
        height: auto;
        padding: 1 0;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(ALGOGATORS_THEME)
        self.theme = "algoterminal"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="launch-bar"):
            yield Static("»", id="launch-prompt")
            yield Input(
                placeholder="Describe a strategy idea and press Enter to start it...",
                id="launch-input",
            )
        with TabbedContent(id="main-tabs"):
            with TabPane("Strategies", id="tab-research"):
                yield ResearchPane()
            with TabPane("Data Universes", id="tab-data"):
                yield DataPane()
            with TabPane("Compare", id="tab-compare"):
                yield ComparePane()
            with TabPane("Design", id="tab-design"):
                yield DesignPane()
        yield Footer()

    def on_mount(self) -> None:
        ensure_dirs()
        self.push_screen(SplashScreen())

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "tab-design":
            self.query_one(DesignPane).refresh_records()
        elif event.pane.id == "tab-compare":
            self.query_one(ComparePane).refresh_items()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "launch-input":
            return
        idea = event.value.strip()
        if not idea:
            return
        event.input.value = ""
        self._launch_strategy_idea(idea)

    def _launch_strategy_idea(self, idea: str) -> None:
        title = idea if len(idea) <= _TITLE_MAX_LEN else idea[: _TITLE_MAX_LEN - 3] + "..."
        self.push_screen(
            HypothesisModal(prefill_title=title, prefill_thesis=idea),
            self._on_quick_launch_created,
        )

    def _on_quick_launch_created(self, result: tuple[Hypothesis, ResearchRecord] | None) -> None:
        if result is None:
            return
        _hypothesis, record = result
        self.query_one(ResearchPane).refresh_records()
        design = self.query_one(DesignPane)
        design.refresh_records()
        design.select_record(record)
        self.query_one("#main-tabs", TabbedContent).active = "tab-design"
        self.notify(f"Saved {record.slug}/{record.version} — describe what it should do and send it to an agent.")


def run() -> None:
    ensure_dirs()
    AlgoTerminalApp().run()
