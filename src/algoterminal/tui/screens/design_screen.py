"""Design tab: pick a strategy on the left, describe what it should do at
the top right, and an AI coding agent (Claude Code, Codex, or a
locally-registered custom agent, your choice) writes it into that strategy's
strategy.py -- and refreshes its C++ trade-engine stub to match. The code
itself is also directly editable below, and the record's folder can be
jumped to in Explorer/Finder or opened in VS Code.

The agent row also lets you register your own local terminal agent (any CLI
that reads a prompt from stdin) as an extra engine option, and download the
scripts that define how prompts get built, for wiring the same contract into
an off-path agent of your own.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Select, Static, TextArea

from algoterminal.research.cpp_export import export_cpp_stub
from algoterminal.research.custom_agents import CustomAgent, add_custom_agent, list_custom_agents
from algoterminal.research.design_agent import ENGINE_LABELS, Engine, available_engines, run_edit
from algoterminal.research.methodology import scaffold_strategy
from algoterminal.research.script_export import export_prompt_scripts
from algoterminal.research.storage import ResearchRecord, list_slugs, list_versions
from algoterminal.theme import ORANGE
from algoterminal.tui.os_actions import can_open_file_location, find_vscode, open_file_location, open_in_vscode
from algoterminal.tui.screens.add_agent_modal import AddAgentModal
from algoterminal.tui.widgets.thinking_indicator import ThinkingIndicator

_NO_SELECTION_MESSAGE = "Select a strategy on the left."
_NO_ENGINE_MESSAGE = "No AI CLI found on PATH and no custom agent registered — install Claude Code/Codex CLI, or add your own with + Agent."


def _agent_label(agent: Engine | CustomAgent) -> str:
    if isinstance(agent, CustomAgent):
        return f"{agent.name} (custom)"
    return ENGINE_LABELS[agent]


class DesignPane(Horizontal):
    """Left: table of strategies. Right: prompt bar + editable strategy.py."""

    def __init__(self) -> None:
        super().__init__()
        self._records: list[ResearchRecord] = []
        self._selected: ResearchRecord | None = None
        self._agent_options: list[Engine | CustomAgent] = []
        self._engine: Engine | CustomAgent | None = None
        self._vscode_available = False
        self._folder_openable = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="design-records-col"):
            yield DataTable(id="design-records-table", cursor_type="row")
            yield Static(id="design-detail")
        with Vertical(id="design-code-col"):
            with Horizontal(id="design-prompt-row"):
                yield Select([], id="design-engine", allow_blank=True, prompt="AI")
                yield Input(
                    placeholder="Describe what this strategy should do, then press Enter...",
                    id="design-prompt",
                )
                yield Button("Send", id="design-send", variant="primary")
            with Horizontal(id="design-agent-row"):
                yield Button("+ Agent", id="design-add-agent")
                yield Button("Download Scripts", id="design-download-scripts")
            yield Static(id="design-status")
            yield ThinkingIndicator(id="design-thinking")
            yield TextArea.code_editor("", language="python", id="design-code")
            with Horizontal(id="design-code-buttons"):
                yield Button("Save", id="design-save")
                yield Button("Reload from disk", id="design-reload")
                yield Button("Open Folder", id="design-open-folder")
                yield Button("Open in VS Code", id="design-open-vscode")

    def on_mount(self) -> None:
        table = self.query_one("#design-records-table", DataTable)
        table.add_columns("Nickname", "Version", "Title")
        self.refresh_records()
        self._refresh_engine_options()
        self._vscode_available = find_vscode() is not None
        self._folder_openable = can_open_file_location()
        self._set_editing_enabled(False)

    def _refresh_engine_options(self) -> None:
        self._agent_options = [*available_engines(), *list_custom_agents()]
        select = self.query_one("#design-engine", Select)
        select.set_options((_agent_label(agent), agent) for agent in self._agent_options)
        if self._agent_options:
            self._engine = self._agent_options[0]
            select.value = self._engine
        else:
            self._engine = None
            status = self.query_one("#design-status", Static)
            status.update(f"[dim]{_NO_ENGINE_MESSAGE}[/dim]")
        if self._selected is not None:
            self._set_editing_enabled(True)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "design-engine":
            self._engine = event.value if isinstance(event.value, (Engine, CustomAgent)) else None

    def refresh_records(self) -> None:
        self._records = []
        table = self.query_one("#design-records-table", DataTable)
        table.clear()
        for slug in list_slugs():
            for record in list_versions(slug):
                try:
                    title = record.load_hypothesis().title
                except Exception:
                    title = "(unreadable)"
                self._records.append(record)
                table.add_row(record.slug, record.version, title)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "design-records-table":
            return
        row_index = event.cursor_row
        if 0 <= row_index < len(self._records):
            self._selected = self._records[row_index]
            self._render_detail()
            self._load_code()
            self._set_editing_enabled(True)

    def select_record(self, record: ResearchRecord) -> None:
        """Programmatically select `record`, e.g. right after it's created elsewhere."""
        for index, candidate in enumerate(self._records):
            if candidate.slug == record.slug and candidate.version == record.version:
                self.query_one("#design-records-table", DataTable).move_cursor(row=index)
                self._selected = candidate
                self._render_detail()
                self._load_code()
                self._set_editing_enabled(True)
                return

    def _render_detail(self) -> None:
        detail = self.query_one("#design-detail", Static)
        record = self._selected
        if record is None:
            detail.update("No strategy selected.")
            return
        try:
            hyp = record.load_hypothesis()
        except Exception:
            detail.update(f"`{record.slug}/{record.version}`\n\n[dim]Could not read hypothesis.yaml[/dim]")
            return
        detail.update(
            f"[bold {ORANGE}]{hyp.title}[/]\n"
            f"`{record.slug}/{record.version}`\n\n"
            f"{hyp.thesis}\n\n"
            f"Universe: {hyp.universe} ({', '.join(hyp.symbols)})\n"
            f"Expected edge: {hyp.expected_edge}"
        )

    def _load_code(self) -> None:
        code = self.query_one("#design-code", TextArea)
        record = self._selected
        if record is None:
            code.text = ""
            return
        if record.strategy_path.exists():
            code.text = record.strategy_path.read_text(encoding="utf-8")
        else:
            code.text = (
                "# No strategy.py yet for this record.\n"
                "# Describe what it should do above and send it to Claude,\n"
                "# or press Save to scaffold the three required functions here first.\n"
            )

    def _set_editing_enabled(self, enabled: bool) -> None:
        have_engine = bool(self._agent_options)
        for widget_id in ("#design-code", "#design-save", "#design-reload"):
            self.query_one(widget_id).disabled = not enabled
        self.query_one("#design-engine", Select).disabled = not (enabled and have_engine)
        self.query_one("#design-prompt", Input).disabled = not (enabled and have_engine)
        self.query_one("#design-send", Button).disabled = not (enabled and have_engine)
        self.query_one("#design-open-folder", Button).disabled = not (enabled and self._folder_openable)
        self.query_one("#design-open-vscode", Button).disabled = not (enabled and self._vscode_available)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "design-send":
            self._send_to_agent()
        elif event.button.id == "design-save":
            self._save_code()
        elif event.button.id == "design-reload":
            self._load_code()
            self.notify("Reloaded from disk.")
        elif event.button.id == "design-open-folder":
            self._open_folder()
        elif event.button.id == "design-open-vscode":
            self._open_vscode()
        elif event.button.id == "design-add-agent":
            self._add_agent()
        elif event.button.id == "design-download-scripts":
            self._download_scripts()

    def _add_agent(self) -> None:
        self.app.push_screen(AddAgentModal(), self._on_agent_added)

    def _on_agent_added(self, agent: CustomAgent | None) -> None:
        if agent is None:
            return
        add_custom_agent(agent)
        self._refresh_engine_options()
        self.notify(f"Added {agent.name!r} as an agent option.")

    def _download_scripts(self) -> None:
        try:
            zip_path = export_prompt_scripts()
        except OSError as e:
            self.notify(f"Couldn't export scripts: {e}", severity="error")
            return
        self.notify(f"Scripts exported to {zip_path}")
        if self._folder_openable:
            try:
                open_file_location(zip_path)
            except OSError:
                pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "design-prompt":
            self._send_to_agent()

    def _open_folder(self) -> None:
        if self._selected is None:
            self.notify(_NO_SELECTION_MESSAGE, severity="warning")
            return
        record = self._selected
        target = record.strategy_path if record.strategy_path.exists() else record.path
        try:
            open_file_location(target)
        except OSError as e:
            self.notify(f"Couldn't open file location: {e}", severity="error")

    def _open_vscode(self) -> None:
        if self._selected is None:
            self.notify(_NO_SELECTION_MESSAGE, severity="warning")
            return
        record = self._selected
        target: Path = record.strategy_path if record.strategy_path.exists() else record.path
        try:
            open_in_vscode(target)
        except (OSError, FileNotFoundError) as e:
            self.notify(f"Couldn't open VS Code: {e}", severity="error")

    def _send_to_agent(self) -> None:
        if self._selected is None:
            self.notify(_NO_SELECTION_MESSAGE, severity="warning")
            return
        if self._engine is None:
            self.notify(_NO_ENGINE_MESSAGE, severity="warning")
            return
        prompt_input = self.query_one("#design-prompt", Input)
        instruction = prompt_input.value.strip()
        if not instruction:
            self.notify("Type what you want the strategy to do first.", severity="warning")
            return

        record = self._selected
        engine = self._engine
        if not record.strategy_path.exists():
            scaffold_strategy(record, record.load_hypothesis())
            self._load_code()

        self.query_one("#design-status", Static).update("")
        self._busy(True)
        self.notify(f"Sending instruction to {_agent_label(engine)} for {record.slug}/{record.version}...")
        self._run_agent_worker(engine, record, instruction)

    def _busy(self, busy: bool) -> None:
        self.query_one("#design-prompt", Input).disabled = busy
        self.query_one("#design-send", Button).disabled = busy
        self.query_one("#design-engine", Select).disabled = busy
        self.query_one("#design-thinking", ThinkingIndicator).busy = busy

    @work(exclusive=True, thread=True)
    def _run_agent_worker(self, engine: Engine | CustomAgent, record: ResearchRecord, instruction: str) -> None:
        ok, message = run_edit(engine, record, instruction)
        self.app.call_from_thread(self._after_agent, engine, record, ok, message)

    def _after_agent(self, engine: Engine | CustomAgent, record: ResearchRecord, ok: bool, message: str) -> None:
        self._busy(False)
        status = self.query_one("#design-status", Static)
        color = "green" if ok else "red"
        status.update(f"[{color}]{message}[/]")
        if ok:
            self.query_one("#design-prompt", Input).value = ""
            try:
                export_cpp_stub(record, record.load_hypothesis())
            except Exception:
                pass
        if record is self._selected:
            self._load_code()
        self.refresh_records()
        label = _agent_label(engine)
        self.notify(f"{label} finished." if ok else f"{label} failed — see status below the prompt.", severity="information" if ok else "error")

    def _save_code(self) -> None:
        if self._selected is None:
            self.notify(_NO_SELECTION_MESSAGE, severity="warning")
            return
        code = self.query_one("#design-code", TextArea)
        self._selected.strategy_path.write_text(code.text, encoding="utf-8")
        self.notify(f"Saved {self._selected.strategy_path}.")
