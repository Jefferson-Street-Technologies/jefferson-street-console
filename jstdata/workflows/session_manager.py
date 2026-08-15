"""Host-level session modal: list, remove, and inspect session resources."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from ..client import JSTDataClient
from ..models import Entity, Metric, Series
from ..session import Session

_PLACEHOLDER = "Highlight an item and press i to inspect."


def _resource_type(resource: Any) -> str:
    if isinstance(resource, Series):
        return "series"
    if isinstance(resource, Entity):
        return "entity"
    if isinstance(resource, Metric):
        return "metric"
    return "series"


class SessionResourceRow(ListItem):
    """One staged resource in the session list (single compact line)."""

    def __init__(self, resource: Any) -> None:
        super().__init__()
        self.resource = resource
        self.resource_type = _resource_type(resource)

    def compose(self) -> ComposeResult:
        name = getattr(self.resource, "label", getattr(self.resource, "name", "Unknown"))
        rtype = self.resource_type.upper()
        # One label keeps ListItem height stable across resizes.
        yield Label(
            f"{rtype:<8} {name}  [{self.resource.id}]",
            classes="sess-row-label",
        )


class SessionManagerModal(ModalScreen[None]):
    """Shared session browser: remove items, inspect API payloads."""

    DEFAULT_CSS = """
    SessionManagerModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #session-mgr-container {
        width: 90%;
        height: 80%;
        max-width: 140;
        max-height: 40;
        border: thick #4ade80;
        background: #111111;
        padding: 1 1;
    }

    #session-mgr-title {
        text-style: bold;
        color: #4ade80;
        text-align: center;
        height: 1;
        margin-bottom: 1;
    }

    #session-mgr-body {
        height: 1fr;
        width: 100%;
    }

    #session-list-pane {
        width: 1fr;
        height: 100%;
        border-right: solid #333;
        padding-right: 1;
    }

    #session-inspect-pane {
        width: 1fr;
        height: 100%;
        padding-left: 1;
    }

    .session-pane-header {
        color: #4ade80;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }

    #session-resource-list {
        height: 1fr;
        width: 100%;
        background: #0a0a0a;
        border: solid #222;
    }

    SessionResourceRow {
        height: 1;
        min-height: 1;
        max-height: 1;
        width: 100%;
        padding: 0 1;
        overflow: hidden;
    }

    SessionResourceRow:hover,
    SessionResourceRow.-highlighted {
        background: #1a3a1a;
    }

    .sess-row-label {
        width: 100%;
        height: 1;
        color: #e0e0e0;
        overflow: hidden;
    }

    ListView > ListItem {
        height: 1;
        min-height: 1;
        max-height: 1;
    }

    #session-inspect-payload {
        height: 1fr;
        width: 100%;
        background: #0a0a0a;
        border: solid #222;
        color: #e0e0e0;
        padding: 1;
        overflow-y: auto;
        overflow-x: auto;
    }

    #session-mgr-hint {
        color: #888;
        height: 1;
        margin-top: 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("i", "inspect", "Inspect"),
        Binding("backspace", "remove", "Remove"),
        Binding("delete", "remove", "Remove", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    def __init__(
        self,
        client: JSTDataClient,
        session: Session,
        basket: list[Any],
    ) -> None:
        super().__init__()
        self.client = client
        self.session = session
        self.basket = basket
        self._inspected_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="session-mgr-container"):
            yield Label("SESSION // STAGED RESOURCES", id="session-mgr-title")
            with Horizontal(id="session-mgr-body"):
                with Vertical(id="session-list-pane"):
                    yield Label("RESOURCES", classes="session-pane-header")
                    yield ListView(id="session-resource-list")
                with Vertical(id="session-inspect-pane"):
                    yield Label("INSPECT", classes="session-pane-header")
                    yield Static(_PLACEHOLDER, id="session-inspect-payload", markup=False)
            yield Label(
                "[bold]i[/bold] inspect  //  [bold]backspace[/bold] remove  //  "
                "[bold]j[/bold]/[bold]k[/bold] or [bold]↑[/bold]/[bold]↓[/bold]  //  [bold]esc[/bold] close",
                id="session-mgr-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._rebuild_list()
        self.query_one("#session-resource-list", ListView).focus()

    def _rebuild_list(self) -> None:
        list_view = self.query_one("#session-resource-list", ListView)
        list_view.clear()
        if not self.basket:
            list_view.append(
                ListItem(Label("Session is empty", classes="sess-row-label"), disabled=True)
            )
            self._show_placeholder()
            return
        for item in self.basket:
            list_view.append(SessionResourceRow(item))

    def _show_placeholder(self) -> None:
        self._inspected_id = None
        self.query_one("#session-inspect-payload", Static).update(_PLACEHOLDER)

    def _highlighted_row(self) -> SessionResourceRow | None:
        list_view = self.query_one("#session-resource-list", ListView)
        child = list_view.highlighted_child
        if isinstance(child, SessionResourceRow):
            return child
        return None

    @on(ListView.Highlighted, "#session-resource-list")
    def on_highlight_changed(self, event: ListView.Highlighted) -> None:
        row = event.item if isinstance(event.item, SessionResourceRow) else None
        if row is None or row.resource.id != self._inspected_id:
            self._show_placeholder()

    def action_inspect(self) -> None:
        row = self._highlighted_row()
        if row is None:
            self.notify("Select a resource to inspect", severity="warning")
            return
        self.query_one("#session-inspect-payload", Static).update("Fetching...")
        self._fetch_payload(row.resource_type, row.resource.id)

    @work(exclusive=True)
    async def _fetch_payload(self, resource_type: str, resource_id: str) -> None:
        try:
            data = await asyncio.to_thread(
                self.client.make_request, f"{resource_type}/{resource_id}"
            )
            text = json.dumps(data, indent=2, default=str)
            self._inspected_id = resource_id
            self.query_one("#session-inspect-payload", Static).update(text)
        except Exception as e:
            self._inspected_id = None
            self.query_one("#session-inspect-payload", Static).update(
                f"Inspect failed: {e}"
            )

    def action_remove(self) -> None:
        row = self._highlighted_row()
        if row is None:
            return
        self._remove_resource(row)

    def _remove_resource(self, row: SessionResourceRow) -> None:
        resource = row.resource
        self.session.remove_id(resource.id)
        self.basket[:] = [i for i in self.basket if i.id != resource.id]
        if self._inspected_id == resource.id:
            self._show_placeholder()
        self._rebuild_list()
        self.notify(f"Removed {resource.id}")
        self.query_one("#session-resource-list", ListView).focus()

    def action_cursor_down(self) -> None:
        self.query_one("#session-resource-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#session-resource-list", ListView).action_cursor_up()

    def action_dismiss(self) -> None:
        self.dismiss()
