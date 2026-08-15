"""Host-level find modal: search the catalog and add to the session."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from ..client import JSTDataClient
from ..models import Entity, Metric, Series
from ..session import Session

_PLACEHOLDER = "Highlight a result and press i to inspect."


def _resource_type(resource: Any) -> str:
    if isinstance(resource, Series):
        return "series"
    if isinstance(resource, Entity):
        return "entity"
    if isinstance(resource, Metric):
        return "metric"
    return "series"


def _resource_label(resource: Any) -> str:
    return (
        getattr(resource, "label", None)
        or getattr(resource, "name", None)
        or getattr(resource, "id", "Unknown")
    )


class FindResultRow(ListItem):
    """One search hit in the find modal."""

    def __init__(self, resource: Any) -> None:
        super().__init__()
        self.resource = resource
        self.resource_type = _resource_type(resource)

    def compose(self) -> ComposeResult:
        name = _resource_label(self.resource)
        source = getattr(self.resource, "source", "") or ""
        yield Label(
            f"{self.resource_type.upper():<8} {name}  [{self.resource.id}]"
            + (f"  {source}" if source else ""),
            classes="find-row-label",
        )


class FindModal(ModalScreen[None]):
    """Shared find surface: search, add to session, inspect payloads."""

    DEFAULT_CSS = """
    FindModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #find-container {
        width: 90%;
        height: 80%;
        max-width: 140;
        max-height: 40;
        border: thick #4ade80;
        background: #111111;
        padding: 1 1;
    }

    #find-title {
        text-style: bold;
        color: #4ade80;
        text-align: center;
        height: 1;
        margin-bottom: 1;
    }

    #find-search-input {
        width: 100%;
        background: #0a0a0a;
        border: solid #333;
        margin-bottom: 1;
    }

    #find-body {
        height: 1fr;
        width: 100%;
    }

    #find-results-pane {
        width: 1fr;
        height: 100%;
        border-right: solid #333;
        padding-right: 1;
    }

    #find-inspect-pane {
        width: 1fr;
        height: 100%;
        padding-left: 1;
    }

    .find-pane-header {
        color: #4ade80;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }

    #find-results-list {
        height: 1fr;
        width: 100%;
        background: #0a0a0a;
        border: solid #222;
    }

    FindResultRow {
        height: 1;
        min-height: 1;
        max-height: 1;
        width: 100%;
        padding: 0 1;
        overflow: hidden;
    }

    FindResultRow:hover,
    FindResultRow.-highlighted {
        background: #1a3a1a;
    }

    .find-row-label {
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

    #find-inspect-payload {
        height: 1fr;
        width: 100%;
        background: #0a0a0a;
        border: solid #222;
        color: #e0e0e0;
        padding: 1;
        overflow-y: auto;
        overflow-x: auto;
    }

    #find-hint {
        color: #888;
        height: 1;
        margin-top: 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("i", "inspect", "Inspect"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    def __init__(self, client: JSTDataClient, session: Session) -> None:
        super().__init__()
        self.client = client
        self.session = session
        self.search_task: asyncio.Task[None] | None = None
        self._inspected_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="find-container"):
            yield Label("FIND // ADD TO SESSION", id="find-title")
            yield Input(
                placeholder="Search metrics, entities, series...",
                id="find-search-input",
            )
            with Horizontal(id="find-body"):
                with Vertical(id="find-results-pane"):
                    yield Label("RESULTS", classes="find-pane-header")
                    yield ListView(id="find-results-list")
                with Vertical(id="find-inspect-pane"):
                    yield Label("INSPECT", classes="find-pane-header")
                    yield Static(_PLACEHOLDER, id="find-inspect-payload", markup=False)
            yield Label(
                "[bold]enter[/bold] focus/add  //  [bold]i[/bold] inspect  //  "
                "[bold]j[/bold]/[bold]k[/bold] or [bold]↑[/bold]/[bold]↓[/bold]  //  [bold]esc[/bold] close",
                id="find-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self.query_one("#find-search-input", Input).focus()

    def _show_placeholder(self) -> None:
        self._inspected_id = None
        self.query_one("#find-inspect-payload", Static).update(_PLACEHOLDER)

    def _highlighted_row(self) -> FindResultRow | None:
        list_view = self.query_one("#find-results-list", ListView)
        child = list_view.highlighted_child
        if isinstance(child, FindResultRow):
            return child
        return None

    def _add_resource(self, resource: Any) -> bool:
        if isinstance(resource, Metric):
            added = self.session.add_metric(resource.id)
        elif isinstance(resource, Entity):
            added = self.session.add_entity(resource.id)
        elif isinstance(resource, Series):
            added = self.session.add_series(resource.id)
        elif resource.id in self.session.resource_ids():
            return False
        else:
            added = self.session.add_series(resource.id)
        if added and hasattr(self.app, "remember_label"):
            self.app.remember_label(resource.id, _resource_label(resource))
        return added

    @on(Input.Changed, "#find-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        if self.search_task:
            self.search_task.cancel()
        if len(event.value.strip()) < 2:
            self.query_one("#find-results-list", ListView).clear()
            self._show_placeholder()
            return
        self.search_task = asyncio.create_task(self._do_search(event.value.strip()))

    async def _do_search(self, query: str) -> None:
        try:
            await asyncio.sleep(0.3)
            results = await asyncio.to_thread(self.client.search, query, limit=20)
            list_view = self.query_one("#find-results-list", ListView)
            list_view.clear()
            self._show_placeholder()
            for r in results:
                list_view.append(FindResultRow(r))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.notify(f"Search error: {e}", severity="error")

    @on(Input.Submitted, "#find-search-input")
    def on_search_submit(self) -> None:
        self.query_one("#find-results-list", ListView).focus()

    @on(ListView.Selected, "#find-results-list")
    def on_result_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, FindResultRow):
            return
        resource = event.item.resource
        if not self._add_resource(resource):
            self.notify(f"{resource.id} is already in session", severity="warning")
            return
        self.notify(f"Added {resource.id} to session")

    @on(ListView.Highlighted, "#find-results-list")
    def on_highlight_changed(self, event: ListView.Highlighted) -> None:
        row = event.item if isinstance(event.item, FindResultRow) else None
        if row is None or row.resource.id != self._inspected_id:
            self._show_placeholder()

    def action_inspect(self) -> None:
        if isinstance(self.focused, Input):
            return
        row = self._highlighted_row()
        if row is None:
            self.notify("Select a result to inspect", severity="warning")
            return
        self.query_one("#find-inspect-payload", Static).update("Fetching...")
        self._fetch_payload(row.resource_type, row.resource.id)

    @work(exclusive=True)
    async def _fetch_payload(self, resource_type: str, resource_id: str) -> None:
        try:
            data = await asyncio.to_thread(
                self.client.make_request, f"{resource_type}/{resource_id}"
            )
            text = json.dumps(data, indent=2, default=str)
            self._inspected_id = resource_id
            self.query_one("#find-inspect-payload", Static).update(text)
        except Exception as e:
            self._inspected_id = None
            self.query_one("#find-inspect-payload", Static).update(
                f"Inspect failed: {e}"
            )

    def action_cursor_down(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            return
        self.query_one("#find-results-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            return
        self.query_one("#find-results-list", ListView).action_cursor_up()

    def action_dismiss(self) -> None:
        self.dismiss()
