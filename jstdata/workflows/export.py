"""Shared export modal for all workflow steps."""

from __future__ import annotations

import subprocess
import sys

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from ..session import Session


def copy_to_clipboard(app, text: str) -> bool:
    """Best-effort clipboard write. Returns True on apparent success."""
    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
            return True
        except Exception:
            pass
    try:
        app.copy_to_clipboard(text)
        return True
    except Exception:
        return False


class ExportModal(ModalScreen[None]):
    """Host export surface: Python snippet, CLI command, write session file."""

    DEFAULT_CSS = """
    ExportModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #export-container {
        width: 90;
        max-width: 100%;
        height: auto;
        max-height: 90%;
        border: thick #4ade80;
        background: #111111;
        padding: 1 2;
    }

    #export-header {
        height: 1;
        margin-bottom: 1;
        width: 100%;
    }

    #export-title {
        text-style: bold;
        color: #4ade80;
        width: 1fr;
        text-align: center;
    }

    .export-section {
        color: #4ade80;
        text-style: bold;
        margin-top: 1;
    }

    .export-code {
        background: #0a0a0a;
        color: #e0e0e0;
        padding: 1;
        height: auto;
        max-height: 12;
        border: solid #333;
    }

    .export-row {
        height: auto;
        margin-top: 1;
    }

    #export-path {
        width: 1fr;
    }

    #export-hint {
        color: #888;
        height: 1;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, session: Session, default_path: str) -> None:
        super().__init__()
        self.session = session
        self.default_path = default_path
        self.python_code = session.to_python()
        self.cli_command = session.to_cli()

    def compose(self) -> ComposeResult:
        with Vertical(id="export-container"):
            with Horizontal(id="export-header"):
                yield Label("EXPORT // TAKE IT WITH YOU", id="export-title")

            yield Label("PYTHON", classes="export-section")
            yield Static(self.python_code, classes="export-code", id="export-python")
            yield Button("COPY PYTHON", id="export-copy-python", variant="primary")

            yield Label("CLI", classes="export-section")
            yield Static(self.cli_command, classes="export-code", id="export-cli")
            yield Button("COPY COMMAND", id="export-copy-cli", variant="primary")

            yield Label("WRITE SESSION", classes="export-section")
            with Horizontal(classes="export-row"):
                yield Input(
                    value=self.default_path,
                    placeholder="session.json",
                    id="export-path",
                )
                yield Button("WRITE", id="export-write", variant="success")

            yield Label(
                "[bold]tab[/bold] move  //  [bold]enter[/bold] activate  //  [bold]esc[/bold] close",
                id="export-hint",
                markup=True,
            )

    @on(Button.Pressed, "#export-copy-python")
    def copy_python(self) -> None:
        if copy_to_clipboard(self.app, self.python_code):
            self.notify("Python snippet copied")
        else:
            self.notify("Could not copy to clipboard", severity="error")

    @on(Button.Pressed, "#export-copy-cli")
    def copy_cli(self) -> None:
        if copy_to_clipboard(self.app, self.cli_command):
            self.notify("CLI command copied")
        else:
            self.notify("Could not copy to clipboard", severity="error")

    @on(Button.Pressed, "#export-write")
    def write_session(self) -> None:
        path = self.query_one("#export-path", Input).value.strip()
        if not path:
            self.notify("Enter a session file path", severity="warning")
            return
        try:
            self.session.save(path)
            if hasattr(self.app, "output_path"):
                self.app.output_path = path
            self.notify(f"Session written to {path}")
        except Exception as e:
            self.notify(f"Failed to write session: {e}", severity="error")

    def action_dismiss(self) -> None:
        self.dismiss()


# Back-compat alias during rename
OfframpModal = ExportModal
