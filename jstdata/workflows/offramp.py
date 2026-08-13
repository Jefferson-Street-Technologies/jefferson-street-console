"""Shared offramp modal for all workflows."""

from __future__ import annotations

import subprocess
import sys

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from ..models import Entity, Metric, Series
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


class OfframpModal(ModalScreen[None]):
    """Identical offramp across workflows: Python, CLI, write session."""

    DEFAULT_CSS = """
    OfframpModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #offramp-container {
        width: 90;
        max-width: 100%;
        height: auto;
        max-height: 90%;
        border: thick #4ade80;
        background: #111111;
        padding: 1 2;
    }

    #offramp-title {
        text-style: bold;
        color: #4ade80;
        margin-bottom: 1;
        text-align: center;
    }

    .offramp-section {
        color: #4ade80;
        text-style: bold;
        margin-top: 1;
    }

    .offramp-code {
        background: #0a0a0a;
        color: #e0e0e0;
        padding: 1;
        height: auto;
        max-height: 12;
        border: solid #333;
    }

    .offramp-row {
        height: auto;
        margin-top: 1;
    }

    #offramp-basket-list {
        background: #0a0a0a;
        border: solid #222;
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }
    .off-col-type { width: 12; color: #888; }
    .off-col-name { width: 1fr; color: #fff; }
    .off-col-id   { width: 25; color: #4ade80; }
    .off-remove-btn { min-width: 4; height: 1; margin-left: 1; }

    #offramp-path {
        width: 1fr;
    }

    #offramp-close {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, session: Session, default_path: str, basket: list[Any]) -> None:
        super().__init__()
        self.session = session
        self.default_path = default_path
        self.basket = basket
        self.python_code = session.to_python()
        self.cli_command = session.to_cli()

    def compose(self) -> ComposeResult:
        with Vertical(id="offramp-container"):
            yield Label("OFFRAMP // TAKE IT WITH YOU", id="offramp-title")

            yield Label("CURRENT BASKET", classes="offramp-section")
            with ListView(id="offramp-basket-list"):
                if not self.basket:
                    yield ListItem(Label("[italic #666]Basket is empty[/italic #666]"), disabled=True)
                else:
                    for item in self.basket:
                        name = getattr(item, "label", getattr(item, "name", "Unknown"))
                        res_type = "SERIES" if isinstance(item, Series) else "ENTITY" if isinstance(item, Entity) else "METRIC"
                        yield ListItem(
                            Horizontal(
                                Label(f"{res_type:<10}", classes="off-col-type"),
                                Label(f"{name}", classes="off-col-name"),
                                Label(f"{item.id}", classes="off-col-id"),
                                Button("X", variant="error", classes="off-remove-btn"),
                            )
                        )

            yield Label("PYTHON", classes="offramp-section")
            yield Static(self.python_code, classes="offramp-code", id="offramp-python")
            yield Button("COPY PYTHON", id="offramp-copy-python", variant="primary")

            yield Label("CLI", classes="offramp-section")
            yield Static(self.cli_command, classes="offramp-code", id="offramp-cli")
            yield Button("COPY COMMAND", id="offramp-copy-cli", variant="primary")

            yield Label("WRITE SESSION", classes="offramp-section")
            with Horizontal(classes="offramp-row"):
                yield Input(
                    value=self.default_path,
                    placeholder="session.json",
                    id="offramp-path",
                )
                yield Button("WRITE", id="offramp-write", variant="success")

            yield Button("CLOSE (ESC)", id="offramp-close", variant="error")

    @on(Button.Pressed, "#offramp-copy-python")
    def copy_python(self) -> None:
        if copy_to_clipboard(self.app, self.python_code):
            self.notify("Python snippet copied")
        else:
            self.notify("Could not copy to clipboard", severity="error")

    @on(Button.Pressed, "#offramp-copy-cli")
    def copy_cli(self) -> None:
        if copy_to_clipboard(self.app, self.cli_command):
            self.notify("CLI command copied")
        else:
            self.notify("Could not copy to clipboard", severity="error")

    @on(Button.Pressed, "#offramp-write")
    def write_session(self) -> None:
        path = self.query_one("#offramp-path", Input).value.strip()
        if not path:
            self.notify("Enter a session file path", severity="warning")
            return
        try:
            self.session.save(path)
            # Keep host default path in sync when launched from WorkflowApp
            if hasattr(self.app, "output_path"):
                self.app.output_path = path
            self.notify(f"Session written to {path}")
        except Exception as e:
            self.notify(f"Failed to write session: {e}", severity="error")

    @on(Button.Pressed, ".off-remove-btn")
    def remove_from_basket(self, event: Button.Pressed) -> None:
        # Find the ListItem parent to get the index/resource
        item_widget = event.button.parent.parent # ListItem
        list_view = self.query_one("#offramp-basket-list", ListView)
        
        # We need to find which index this is
        idx = list_view.children.index(item_widget)
        
        # Remove from session and in-memory basket
        resource = self.basket[idx]
        self.session.remove_id(resource.id)
        self.basket.pop(idx)
        
        # Update UI
        item_widget.remove()
        if not self.basket:
            list_view.append(ListItem(Label("[italic #666]Basket is empty[/italic #666]"), disabled=True))
        
        self.notify(f"Removed {resource.id}")
        # Refresh code snippets
        self.python_code = self.session.to_python()
        self.cli_command = self.session.to_cli()
        self.query_one("#offramp-python", Static).update(self.python_code)
        self.query_one("#offramp-cli", Static).update(self.cli_command)

    @on(Button.Pressed, "#offramp-close")
    def close_offramp(self) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
