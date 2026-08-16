"""Console step — general-purpose session editor TUI."""

from __future__ import annotations

import asyncio
from typing import Any, TypeAlias

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static

from ..client import JSTDataClient
from ..models import Entity, EntityRelationship, Metric, Series, Resource as ApiResource
from ..session import Session
from .base import StepArgument, StepBinding, StepSpec, register

Resource: TypeAlias = Series | Entity | Metric | ApiResource
InspectorResource: TypeAlias = Series | Entity | Metric | EntityRelationship


class SearchResultRow(ListItem):
    """A row in the search results list."""

    def __init__(self, resource: Resource):
        super().__init__()
        self.resource = resource

    def compose(self) -> ComposeResult:
        res = self.resource
        name = getattr(res, "label", getattr(res, "name", "Unknown"))
        res_type = (
            "SERIES"
            if isinstance(res, Series)
            else "ENTITY"
            if isinstance(res, Entity)
            else "METRIC"
        )
        source = getattr(res, "source", "N/A")

        yield Horizontal(
            Label(f"{name}", classes="col-name"),
            Label(f"{res.id[:15]:<15}", classes="col-id"),
            Label(f"{source[:10]:<10}", classes="col-src"),
            Label(f"{res_type:<10}", classes="col-type"),
        )


class InspectorResultRow(ListItem):
    """A row in the inspector results list."""

    def __init__(self, resource: InspectorResource):
        super().__init__()
        self.resource = resource

    def compose(self) -> ComposeResult:
        res = self.resource

        if isinstance(res, EntityRelationship):
            name = getattr(res, "target_label", getattr(res, "target_name", res.id)) or ""
            item_id = res.id
            type_str = "REL_ENTITY"
        elif isinstance(res, Entity):
            name = getattr(res, "label", getattr(res, "name", res.id)) or ""
            item_id = res.id
            type_str = "ENTITY"
        elif isinstance(res, Metric):
            name = getattr(res, "label", getattr(res, "name", res.id)) or ""
            item_id = res.id
            type_str = "METRIC"
        elif isinstance(res, Series):
            name = getattr(res, "label", getattr(res, "name", res.id)) or ""
            item_id = res.id
            type_str = "SERIES"
        else:
            name = str(res)
            item_id = "N/A"
            type_str = "UNKNOWN"

        yield Horizontal(
            Label(f"{type_str:<12}", classes="insp-col-type"),
            Label(f"{name[:25]:<25}", classes="insp-col-name"),
            Label(f"{item_id[:15]:<15}", classes="insp-col-id"),
        )


class WorkspaceScreen(Screen):
    """Console workspace: search and related-resource inspection."""

    BINDINGS = [
        Binding("i", "inspect", "Inspect"),
        Binding("j", "cursor_down", "Cursor Down", show=False),
        Binding("k", "cursor_up", "Cursor Up", show=False),
    ]

    DEFAULT_CSS = """
    #workspace-body {
        height: 1fr;
    }

    .pane-container {
        border: solid #222;
        background: #0f0f0f;
    }
    #results-pane { height: 60%; }
    #inspector-pane { height: 40%; border-top: solid #333; }

    .pane-header {
        background: #1a1a1a;
        color: #4ade80;
        padding: 0 1;
        text-style: bold;
        height: 1;
    }
    .table-header {
        height: 1;
        background: #111;
        border-bottom: solid #333;
        padding: 0 1;
    }
    .table-header Label {
        color: #888;
        text-style: bold;
    }

    #results-list {
        height: 1fr;
        background: #0f0f0f;
    }

    .col-name { width: 55%; height: 1; overflow: hidden; }
    .col-id   { width: 25%; height: 1; overflow: hidden; }
    .col-src  { width: 10%; height: 1; overflow: hidden; }
    .col-type { width: 10%; height: 1; overflow: hidden; }

    ListView > ListItem,
    SearchResultRow,
    InspectorResultRow {
        height: 1;
        min-height: 1;
        max-height: 1;
        width: 100%;
        padding: 0 1;
        overflow: hidden;
    }

    SearchResultRow > Horizontal,
    InspectorResultRow > Horizontal {
        height: 1;
        min-height: 1;
        max-height: 1;
        overflow: hidden;
    }

    SearchResultRow:focus,
    SearchResultRow.-highlighted,
    InspectorResultRow:focus,
    InspectorResultRow.-highlighted {
        background: #1a3a1a;
        color: #4ade80;
    }

    #cmd-bar {
        height: 3;
        background: #0f0f0f;
        border-top: solid #4ade80;
        align: left middle;
    }
    #cmd-prompt { color: #4ade80; padding: 0 1; text-style: bold; }
    #search-input {
        width: 1fr;
        background: transparent;
        border: none;
    }
    #help-hint {
        color: #888;
        margin-right: 2;
    }

    #inspector-default-view {
        height: 1fr;
        padding: 1 2;
    }
    #inspector-interactive-view {
        display: none;
        height: 1fr;
        padding: 0 1;
    }
    #inspector-meta {
        color: #4ade80;
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }
    #inspector-search-status {
        color: #eab308;
        height: 1;
        margin-bottom: 0;
    }
    #inspector-search-input {
        background: #111;
        border: none;
        height: 3;
        margin-bottom: 0;
    }
    #inspector-results-list {
        height: 1fr;
        background: #0f0f0f;
    }
    .insp-col-type { width: 12; height: 1; overflow: hidden; color: #888; }
    .insp-col-name { width: 25; height: 1; overflow: hidden; color: #fff; }
    .insp-col-id   { width: 15; height: 1; overflow: hidden; color: #4ade80; }
    """

    def __init__(
        self,
        client: JSTDataClient,
        session: Session,
        taxonomy: str | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.session = session
        self.taxonomy = taxonomy or None
        self.taxonomy_name = taxonomy
        self.taxonomy_entities: list[Entity] = []
        self.taxonomy_metrics: list[Metric] = []

        self.search_task: asyncio.Task[None] | None = None
        self.inspector_search_task: asyncio.Task[None] | None = None
        self.preloaded_entities: list[Entity | EntityRelationship] = []
        self.preloaded_metrics: list[Metric] = []
        self.preloaded_series: list[Series] = []
        self.large_search_space = False
        self.inspector_prefetching = False
        self.current_inspected_resource: Resource | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="workspace-body"):
            with Vertical(classes="pane-container", id="results-pane"):
                yield Label("RESULTS // SEARCH_MATCHES", classes="pane-header", id="results-header")
                with Horizontal(classes="table-header"):
                    yield Label("NAME", classes="col-name")
                    yield Label("ID", classes="col-id")
                    yield Label("SRC", classes="col-src")
                    yield Label("TYPE", classes="col-type")
                yield ListView(id="results-list")

            with Vertical(classes="pane-container", id="inspector-pane"):
                yield Label("INSPECTOR // DATA_DETAILS", classes="pane-header")
                with Vertical(id="inspector-default-view"):
                    yield Static(
                        id="inspector-content",
                        content="Highlight an item and press 'i' to inspect.",
                    )
                with Vertical(id="inspector-interactive-view"):
                    yield Label("", id="inspector-meta")
                    yield Label("", id="inspector-search-status")
                    yield Input(
                        placeholder="Search related entities/metrics...",
                        id="inspector-search-input",
                    )
                    yield ListView(id="inspector-results-list")

        with Horizontal(id="cmd-bar"):
            yield Label(">", id="cmd-prompt")
            yield Input(
                placeholder="SEARCH_DATABASE (ENTITY | METRIC | DATASET) ...",
                id="search-input",
            )
            yield Label("", id="help-hint")

    def on_mount(self) -> None:
        self.query_one("#search-input").focus()
        self._refresh_help_hint()
        if self.taxonomy:
            self._apply_taxonomy_chrome()
            self.run_taxonomy_preload()

    def _apply_taxonomy_chrome(self) -> None:
        label = self.taxonomy_name or self.taxonomy or ""
        self.query_one("#results-header").update(f"RESULTS // TAXONOMY {label}")
        self.query_one("#search-input", Input).placeholder = (
            f"SEARCH WITHIN {label} (ENTITY | METRIC) ..."
        )

    def _show_taxonomy_catalog(self) -> None:
        list_view = self.query_one("#results-list", ListView)
        list_view.clear()
        for resource in [*self.taxonomy_metrics, *self.taxonomy_entities]:
            list_view.append(SearchResultRow(resource))

    @work(exclusive=True)
    async def run_taxonomy_preload(self) -> None:
        """Load taxonomy metadata and a first page of members for the selector."""
        if not self.taxonomy:
            return
        try:
            tax = await asyncio.to_thread(self.client.get_taxonomy, self.taxonomy)
            self.taxonomy_name = tax.name
            self._apply_taxonomy_chrome()
            entities, metrics = await asyncio.gather(
                asyncio.to_thread(
                    self.client.get_taxonomy_entities, self.taxonomy, 50
                ),
                asyncio.to_thread(
                    self.client.get_taxonomy_metrics, self.taxonomy, 50
                ),
            )
            self.taxonomy_entities = list(entities)
            self.taxonomy_metrics = list(metrics)
            self._show_taxonomy_catalog()
        except Exception as e:
            self.notify(f"Could not load taxonomy {self.taxonomy}: {e}", severity="error")

    def _refresh_help_hint(self) -> None:
        app = self.app
        n = getattr(app, "step_count", 1)
        i = getattr(app, "step_index", 0) + 1
        step_id = getattr(app, "current_step_id", "console")
        parts = [
            f"{step_id} {i}/{n}",
        ]
        if self.taxonomy:
            parts.append(f"tax {self.taxonomy}")
        parts.extend(
            [
                "[bold]s[/bold] session",
                "[bold]f[/bold] find",
                "[bold]e[/bold] export",
                "[bold]n[/bold]/[bold]p[/bold]",
                "[bold]q[/bold] quit",
                "[bold]?[/bold]",
            ]
        )
        self.query_one("#help-hint").update(" // ".join(parts))

    def action_inspect(self) -> None:
        """Fetch deep details for highlighted item."""
        list_view = self.query_one("#results-list", ListView)
        if list_view.highlighted_child:
            resource = list_view.highlighted_child.resource
            self._start_inspector_search(resource)

    def action_cursor_down(self) -> None:
        focused = self.focused
        if focused and hasattr(focused, "action_cursor_down"):
            focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        focused = self.focused
        if focused and hasattr(focused, "action_cursor_up"):
            focused.action_cursor_up()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        if self.search_task:
            self.search_task.cancel()
        if len(event.value) < 2:
            if self.taxonomy:
                self._show_taxonomy_catalog()
            else:
                self.query_one("#results-list", ListView).clear()
            return
        self.search_task = asyncio.create_task(self._do_search(event.value))

    async def _do_search(self, query: str) -> None:
        try:
            await asyncio.sleep(0.3)
            if self.taxonomy:
                entities, metrics = await asyncio.gather(
                    asyncio.to_thread(
                        self.client.search_entities,
                        query,
                        taxonomy=self.taxonomy,
                        limit=15,
                    ),
                    asyncio.to_thread(
                        self.client.search_metrics,
                        query,
                        taxonomy=self.taxonomy,
                        limit=15,
                    ),
                )
                results = [*metrics, *entities]
            else:
                results = await asyncio.to_thread(self.client.search, query, limit=20)
            list_view = self.query_one("#results-list", ListView)
            list_view.clear()
            for r in results:
                list_view.append(SearchResultRow(r))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.notify(f"Search error: {e}", severity="error")

    @on(Input.Submitted, "#search-input")
    def on_search_submit(self) -> None:
        self.query_one("#results-list", ListView).focus()

    @on(ListView.Selected, "#results-list")
    def add_to_session(self, event: ListView.Selected) -> None:
        resource = event.item.resource
        if not self._add_resource_to_session(resource):
            self.notify(f"{resource.id} is already in session", severity="warning")
            return
        self.notify("Added to session")

    def _resource_label(self, resource: Resource) -> str:
        return getattr(resource, "label", None) or getattr(resource, "name", None) or resource.id

    def _add_resource_to_session(self, resource: Resource) -> bool:
        """Update the session for a newly staged resource. Returns False if duplicate."""
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
        if added:
            self.app.remember_label(resource.id, self._resource_label(resource))
        return added

    def _start_inspector_search(self, resource: Any) -> None:
        """Switch view to inspector interactive search and begin prefetch."""
        self.query_one("#inspector-default-view").styles.display = "none"
        self.query_one("#inspector-interactive-view").styles.display = "block"

        meta_label = self.query_one("#inspector-meta")
        res_type = (
            "SERIES"
            if isinstance(resource, Series)
            else "ENTITY"
            if isinstance(resource, Entity)
            else "METRIC"
        )
        name = getattr(resource, "label", getattr(resource, "name", "Unknown"))
        meta_label.update(f"{name.upper()} // {res_type} // ID: {resource.id}")

        self.query_one("#inspector-search-status").update("")
        self.query_one("#inspector-search-input").value = ""
        self.query_one("#inspector-results-list", ListView).clear()
        self.query_one("#inspector-search-input").focus()

        self.current_inspected_resource = resource
        self.run_inspector_prefetch(resource)

    @work(exclusive=True)
    async def run_inspector_prefetch(self, resource: Any) -> None:
        status_label = self.query_one("#inspector-search-status")
        status_label.update("[italic green]Fetching related items...[/italic green]")
        self.preloaded_entities = []
        self.preloaded_metrics = []
        self.preloaded_series = []
        self.large_search_space = False
        self.inspector_prefetching = True
        try:
            if isinstance(resource, Entity):
                relations = await asyncio.to_thread(
                    self.client.get_entity_relations, resource.id, limit=201
                )
                metrics = await asyncio.to_thread(
                    self.client.search_metrics, "", entity=resource.id, limit=201
                )
                self.preloaded_entities = relations
                self.preloaded_metrics = metrics
                if len(relations) > 200 or len(metrics) > 200:
                    self.large_search_space = True
                    status_label.update(
                        "[yellow]Large search space (>200 items); server search active[/yellow]"
                    )
                else:
                    status_label.update("")
            elif isinstance(resource, Metric):
                series = await asyncio.to_thread(
                    self.client.get_metric_series, resource.id, limit=201
                )
                entities = await asyncio.to_thread(
                    self.client.search_entities, "", metric=resource.id, limit=201
                )
                self.preloaded_series = series
                self.preloaded_entities = entities
                if len(series) > 200 or len(entities) > 200:
                    self.large_search_space = True
                    status_label.update(
                        "[yellow]Large search space (>200 items); server search active[/yellow]"
                    )
                else:
                    status_label.update("")
            elif isinstance(resource, Series):
                self.preloaded_series = [resource]
                status_label.update("")
        except Exception as e:
            status_label.update(f"[red]Error prefetching: {e}[/red]")
        finally:
            self.inspector_prefetching = False
            current_query = self.query_one("#inspector-search-input").value
            if current_query:
                if self.inspector_search_task:
                    self.inspector_search_task.cancel()
                self.inspector_search_task = asyncio.create_task(
                    self._do_inspector_search(current_query)
                )
            else:
                self._update_inspector_results("", initial=True)

    @on(Input.Changed, "#inspector-search-input")
    def on_inspector_search_changed(self, event: Input.Changed) -> None:
        if self.inspector_prefetching:
            return
        if self.inspector_search_task:
            self.inspector_search_task.cancel()
        self.inspector_search_task = asyncio.create_task(
            self._do_inspector_search(event.value)
        )

    async def _do_inspector_search(self, query: str) -> None:
        try:
            await asyncio.sleep(0.3)
            resource = self.current_inspected_resource
            if not resource:
                return
            if self.large_search_space and len(query) >= 2:
                self.query_one("#inspector-search-status").update(
                    "[italic green]Searching server...[/italic green]"
                )
                if isinstance(resource, Entity):
                    metrics = await asyncio.to_thread(
                        self.client.search_metrics, query, entity=resource.id, limit=50
                    )
                    local_relations = [
                        r
                        for r in self.preloaded_entities
                        if query.lower() in (getattr(r, "id", "") or "").lower()
                        or query.lower() in r.id.lower()
                    ]
                    self._update_inspector_list(local_relations, metrics)
                elif isinstance(resource, Metric):
                    entities = await asyncio.to_thread(
                        self.client.search_entities, query, metric=resource.id, limit=50
                    )
                    local_series = [
                        s
                        for s in self.preloaded_series
                        if query.lower() in (getattr(s, "label", "") or "").lower()
                        or query.lower() in s.id.lower()
                    ]
                    self._update_inspector_list(entities, local_series)
                self.query_one("#inspector-search-status").update(
                    "[yellow]Large search space (>200 items); server search active[/yellow]"
                )
            else:
                self._update_inspector_results(query)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.query_one("#inspector-search-status").update(f"[red]Search error: {e}[/red]")

    def _update_inspector_results(self, query: str, initial: bool = False) -> None:
        query_lower = query.lower()
        filtered_entities = []
        filtered_metrics = []
        filtered_series = []
        for e in self.preloaded_entities:
            label = (
                getattr(
                    e,
                    "target_label",
                    getattr(e, "target_name", getattr(e, "label", getattr(e, "name", ""))),
                )
                or ""
            )
            item_id = e.id
            if not query or query_lower in label.lower() or query_lower in item_id.lower():
                filtered_entities.append(e)
        for m in self.preloaded_metrics:
            label = getattr(m, "label", getattr(m, "name", "")) or ""
            item_id = m.id
            if not query or query_lower in label.lower() or query_lower in item_id.lower():
                filtered_metrics.append(m)
        for s in self.preloaded_series:
            label = getattr(s, "label", getattr(s, "name", "")) or ""
            item_id = s.id
            if not query or query_lower in label.lower() or query_lower in item_id.lower():
                filtered_series.append(s)
        self._update_inspector_list(filtered_entities, filtered_metrics, filtered_series)

    def _update_inspector_list(self, *lists) -> None:
        results_list = self.query_one("#inspector-results-list", ListView)
        results_list.clear()
        count = 0
        for lst in lists:
            for item in lst:
                results_list.append(InspectorResultRow(item))
                count += 1
                if count >= 100:
                    break
            if count >= 100:
                break

    @on(Input.Submitted, "#inspector-search-input")
    def on_inspector_search_submit(self) -> None:
        self.query_one("#inspector-results-list", ListView).focus()

    @on(ListView.Selected, "#inspector-results-list")
    def on_inspector_item_selected(self, event: ListView.Selected) -> None:
        self.add_inspector_item_to_session(event.item.resource)

    @work(exclusive=True)
    async def add_inspector_item_to_session(self, item: Any) -> None:
        try:
            if isinstance(item, EntityRelationship):
                resource = await asyncio.to_thread(self.client.get_entity, item.id)
            elif isinstance(item, (Series, Entity, Metric)):
                resource = item
            else:
                return
            if not self._add_resource_to_session(resource):
                self.notify(f"{resource.id} is already in session", severity="warning")
                return
            self.notify(f"Added {resource.id} to session")
        except Exception as e:
            self.notify(f"Error adding to session: {e}", severity="error")


def create_console_screen(client, session, taxonomy=None, **kwargs):
    return WorkspaceScreen(client, session, taxonomy=taxonomy)


CONSOLE = register(
    StepSpec(
        id="console",
        name="Console",
        description=(
            "General-purpose session editor. Search metrics, entities, and series; "
            "stage resources; inspect related metadata."
        ),
        create_screen=create_console_screen,
        arguments=(
            StepArgument(
                name="taxonomy",
                type="string",
                description=(
                    "Restrict search to entities and metrics in this taxonomy "
                    "(slug, e.g. sec-central-index-key)"
                ),
            ),
        ),
        bindings=(
            StepBinding(
                "i", "inspect", "Inspect related resources for highlighted result"
            ),
            StepBinding(
                "enter",
                "submit",
                "Focus results (from search) / add to session (from results)",
            ),
            StepBinding("j / ↓", "cursor_down", "Move highlight down"),
            StepBinding("k / ↑", "cursor_up", "Move highlight up"),
            StepBinding("escape", "back", "Leave inspector focus"),
        ),
        example="jst run console --taxonomy sec-central-index-key",
    )
)
