"""Modal to register a local terminal agent (a CLI/script already run from
your own terminal) as an extra option in the Design tab's engine picker."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from algoterminal.research.custom_agents import CustomAgent


class AddAgentModal(ModalScreen[CustomAgent | None]):
    """Captures a name and a shell command for a user-owned coding agent."""

    DEFAULT_CSS = """
    AddAgentModal {
        align: center middle;
    }
    #agent-form {
        width: 70;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #agent-form Label {
        margin-top: 1;
    }
    #agent-buttons {
        margin-top: 1;
        height: auto;
        align: right middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-form"):
            yield Label("[bold]Add Terminal Agent[/bold]")
            yield Static(
                "[dim]Any local CLI that reads a prompt from stdin and edits files in "
                "its working directory. The prompt is piped to this command over stdin, "
                "run with the strategy's own record folder as its working directory.[/dim]"
            )
            yield Label("Name")
            yield Input(placeholder="e.g. my-agent", id="agent-name")
            yield Label("Command")
            yield Input(placeholder="e.g. my-agent-cli --edit", id="agent-command")
            with Grid(id="agent-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Add", id="add", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return

        name = self.query_one("#agent-name", Input).value.strip()
        command = self.query_one("#agent-command", Input).value.strip()
        if not (name and command):
            self.notify("Name and command are both required.", severity="error")
            return
        self.dismiss(CustomAgent(name=name, command=command))
