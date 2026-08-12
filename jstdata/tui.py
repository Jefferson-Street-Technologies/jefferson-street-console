from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Input, ListItem, ListView, Static, Label, Button, DataTable
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual import on, work
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, TypeAlias

from .client import JSTDataClient
from .models import Series, Entity, Metric, EntityRelationship, Resource as ApiResource
from .session import Session
from .workflows.base import apply_loaded_session, default_session_path, load_session_or_empty
from .workflows.offramp import OfframpModal, copy_to_clipboard

Resource: TypeAlias = Series | Entity | Metric | ApiResource
InspectorResource: TypeAlias = Series | Entity | Metric | EntityRelationship

# --- Custom Widgets ---

class SearchResultRow(ListItem):
    """A row in the search results list."""
    def __init__(self, resource: Resource):
        super().__init__()
        self.resource = resource

    def compose(self) -> ComposeResult:
        res = self.resource
        name = getattr(res, "label", getattr(res, "name", "Unknown"))
        res_type = "SERIES" if isinstance(res, Series) else "ENTITY" if isinstance(res, Entity) else "METRIC"
        source = getattr(res, "source", "N/A")
        
        yield Horizontal(
            Label(f"{name}", classes="col-name"),
            Label(f"{res.id[:15]:<15}", classes="col-id"),
            Label(f"{source[:10]:<10}", classes="col-src"),
            Label(f"{res_type:<10}", classes="col-type"),
        )

class BasketHeader(ListItem):
    """A header in the staging basket list."""
    def __init__(self, title: str):
        super().__init__(disabled=True)
        self.title = title

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="basket-header-label")

class BasketItem(ListItem):
    """An item in the staging basket."""
    def __init__(self, resource: Resource):
        super().__init__()
        self.resource = resource

    def compose(self) -> ComposeResult:
        res = self.resource
        name = getattr(res, "label", getattr(res, "name", "Unknown"))
        subtext = f"{getattr(res, 'source', 'API')} // {getattr(res, 'frequency', 'DATA')}"
        
        with Horizontal():
            with Vertical():
                yield Label(f"[bold]{name}[/bold]", classes="basket-item-name")
                yield Label(subtext, classes="basket-item-subtext")
            yield Button("X", variant="error", classes="remove-btn")

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

# --- Screens ---

class WorkspaceScreen(Screen):
    """The main research workspace (Tab 1)."""

    BINDINGS = [
        Binding("i", "inspect", "Inspect"),
        Binding("ctrl+e", "execute_query", "Execute Query"),
        Binding("shift+enter", "execute_query", "Execute Query"),
        Binding("backspace", "remove_basket_item", "Remove Basket Item"),
        Binding("j", "cursor_down", "Cursor Down", show=False),
        Binding("k", "cursor_up", "Cursor Up", show=False),
        Binding("l", "load_session", "Load Session"),
    ]

    def __init__(
        self,
        client: JSTDataClient,
        session: Session,
        basket: list[Resource],
    ) -> None:
        super().__init__()
        self.client = client
        self.session = session
        self.basket = basket

        self.search_task: asyncio.Task[None] | None = None
        self.inspector_search_task: asyncio.Task[None] | None = None
        self.preloaded_entities: list[Entity | EntityRelationship] = []
        self.preloaded_metrics: list[Metric] = []
        self.preloaded_series: list[Series] = []
        self.large_search_space = False
        self.inspector_prefetching = False
        self.current_inspected_resource: Resource | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace-body"):
            with Vertical(id="left-column"):
                with Vertical(classes="pane-container", id="results-pane"):
                    yield Label("RESULTS // SEARCH_MATCHES", classes="pane-header")
                    with Horizontal(classes="table-header"):
                        yield Label("NAME", classes="col-name")
                        yield Label("ID", classes="col-id")
                        yield Label("SRC", classes="col-src")
                        yield Label("TYPE", classes="col-type")
                    yield ListView(id="results-list")
                
                with Vertical(classes="pane-container", id="inspector-pane"):
                    yield Label("INSPECTOR // DATA_DETAILS", classes="pane-header")
                    with Vertical(id="inspector-default-view"):
                        yield Static(id="inspector-content", content="Highlight an item and press 'i' to inspect.")
                    with Vertical(id="inspector-interactive-view"):
                        yield Label("", id="inspector-meta")
                        yield Label("", id="inspector-search-status")
                        yield Input(placeholder="Search related entities/metrics...", id="inspector-search-input")
                        yield ListView(id="inspector-results-list")
            
            with Vertical(id="right-column", classes="pane-container"):
                yield ListView(id="basket-list")
                with Vertical(id="basket-summary"):
                    with Horizontal():
                        with Vertical():
                            yield Label("TOTAL SERIES", classes="stat-label")
                            yield Label("0", id="stat-series", classes="stat-value")
                        with Vertical():
                            yield Label("EST. OBS.", classes="stat-label")
                            yield Label("0", id="stat-obs", classes="stat-value")
        
        with Horizontal(id="cmd-bar"):
            yield Label(">", id="cmd-prompt")
            yield Input(placeholder="SEARCH_DATABASE (ENTITY | METRIC | DATASET) ...", id="search-input")
            yield Label("Press [bold]?[/bold] for help // [bold]s[/bold] save // [bold]o[/bold] offramp // [bold]ctrl+e[/bold] run", id="help-hint")

    def on_mount(self) -> None:
        self.query_one("#search-input").focus()
        if self.session.resource_ids() and not self.basket:
            self._hydrate_basket_from_session()
        self._rebuild_basket_list()
        self._update_stats()

    def load_session(self, filepath: str) -> None:
        """Load a session from JSON and refresh the staging basket."""
        try:
            loaded = Session.load(filepath)
            apply_loaded_session(self.session, loaded)
            self._hydrate_basket_from_session()
            self._rebuild_basket_list()
            self._update_stats()
            self.notify(f"Loaded {len(self.session.resource_ids())} items from session")
        except FileNotFoundError:
            self.notify(f"Session file not found: {filepath}", severity="error")
        except json.JSONDecodeError as e:
            self.notify(f"Invalid JSON in session file: {e}", severity="error")

    def _hydrate_basket_from_session(self) -> None:
        """Rebuild the display basket from session IDs (labels via API)."""
        self.basket.clear()
        ids = self.session.resource_ids()
        if not ids:
            return

        labels = {r.id: r.label for r in self.client.get_resources(ids)}
        for mid in self.session.metric:
            self.basket.append(Metric(id=mid, name=labels.get(mid, mid)))
        for eid in self.session.entity:
            self.basket.append(Entity(id=eid, label=labels.get(eid, eid)))
        for sid in self.session.series:
            self.basket.append(
                Series(
                    id=sid,
                    label=labels.get(sid, sid),
                    frequency="",
                    source="",
                    units="",
                    seasonal_adjustment="",
                    last_updated=datetime.min,
                    metric_id="",
                )
            )

    def _load_session_result(self, filepath: str | None) -> None:
        if filepath:
            self.load_session(filepath)

    def action_inspect(self) -> None:
        """Fetch deep details for highlighted item."""
        list_view = self.query_one("#results-list", ListView)
        if list_view.highlighted_child:
            resource = list_view.highlighted_child.resource
            self._start_inspector_search(resource)
    def action_execute_query(self) -> None:
        """Execute the query for the current session."""
        if self.session.is_empty():
            self.notify("Basket is empty", severity="warning")
            return
        self.app.push_screen(ExplorerScreen(self.client, self.session))
    def action_load_session(self) -> None:
        """Load session from a prompt file."""
        default = getattr(self.app, "output_path", "session.json")
        self.app.push_screen(
            SessionModal("Load session from file:", "session.json", default=default),
            self._load_session_result,
        )
    def action_remove_basket_item(self) -> None:
        """Remove the highlighted item in the active basket list."""
        try:
            basket_list = self.query_one("#basket-list", ListView)
        except Exception:
            return
        if basket_list.has_focus and basket_list.highlighted_child:
            item_widget = basket_list.highlighted_child  # BasketItem
            if isinstance(item_widget, BasketItem):
                resource = item_widget.resource
                self.session.remove_id(resource.id)
                self.basket[:] = [i for i in self.basket if i.id != resource.id]
                self._rebuild_basket_list()
                self._update_stats()
                self.notify("Removed from basket")
                return
    def action_cursor_down(self) -> None:
        """Move cursor/highlight down in the currently focused list or component."""
        focused = self.focused
        if focused and hasattr(focused, "action_cursor_down"):
            focused.action_cursor_down()
    def action_cursor_up(self) -> None:
        """Move cursor/highlight up in the currently focused list or component."""
        focused = self.focused
        if focused and hasattr(focused, "action_cursor_up"):
            focused.action_cursor_up()
    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        if self.search_task:
            self.search_task.cancel()
        if len(event.value) < 2:
            self.query_one("#results-list", ListView).clear()
            return
        self.search_task = asyncio.create_task(self._do_search(event.value))
    async def _do_search(self, query: str) -> None:
        try:
            await asyncio.sleep(0.3)
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
    def add_to_basket(self, event: ListView.Selected) -> None:
        resource = event.item.resource
        if not self._add_resource_to_session(resource):
            return
        self.basket.append(resource)
        self._rebuild_basket_list()
        self.notify("Added to basket")
        self._update_stats()

    @on(Button.Pressed, ".remove-btn")
    def remove_from_basket(self, event: Button.Pressed) -> None:
        item_widget = event.button.parent.parent  # BasketItem
        resource = item_widget.resource
        self.session.remove_id(resource.id)
        self.basket[:] = [i for i in self.basket if i.id != resource.id]
        self._rebuild_basket_list()
        self._update_stats()

    def _add_resource_to_session(self, resource: Resource) -> bool:
        """Update the session for a newly staged resource. Returns False if duplicate."""
        if isinstance(resource, Metric):
            return self.session.add_metric(resource.id)
        if isinstance(resource, Entity):
            return self.session.add_entity(resource.id)
        if isinstance(resource, Series):
            return self.session.add_series(resource.id)
        # Untyped API resource: treat as series only if already classified elsewhere
        if resource.id in self.session.resource_ids():
            return False
        return self.session.add_series(resource.id)
    def _rebuild_basket_list(self) -> None:
        try:
            basket_list = self.query_one("#basket-list", ListView)
        except Exception:
            return
        
        # Save the current highlighted item's resource ID so we can restore the highlight
        old_highlighted_id = None
        if basket_list.highlighted_child and isinstance(basket_list.highlighted_child, BasketItem):
            old_highlighted_id = basket_list.highlighted_child.resource.id
            
        basket_list.clear()
        
        # Add Metrics & Series Header
        basket_list.append(BasketHeader("STAGING_BASKET // METRICS & SERIES"))
        
        # Add Metrics & Series items
        for item in self.basket:
            if not isinstance(item, Entity):
                basket_list.append(BasketItem(item))
                
        # Add Entities Header
        basket_list.append(BasketHeader("STAGING_BASKET // ENTITIES"))
        
        # Add Entity items
        for item in self.basket:
            if isinstance(item, Entity):
                basket_list.append(BasketItem(item))
                
        # Restore highlight if possible
        if old_highlighted_id is not None:
            for index, child in enumerate(basket_list.children):
                if isinstance(child, BasketItem) and child.resource.id == old_highlighted_id:
                    basket_list.index = index
                    break
    def _update_stats(self) -> None:
        self.query_one("#stat-series").update(str(len(self.session.resource_ids())))
        self.query_one("#stat-obs").update("---")
    def _start_inspector_search(self, resource: Any) -> None:
        """Switch view to inspector interactive search and begin prefetch."""
        self.query_one("#inspector-default-view").styles.display = "none"
        self.query_one("#inspector-interactive-view").styles.display = "block"
        
        meta_label = self.query_one("#inspector-meta")
        res_type = "SERIES" if isinstance(resource, Series) else "ENTITY" if isinstance(resource, Entity) else "METRIC"
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
        """Fetch relations & metrics/series to determine search space size."""
        status_label = self.query_one("#inspector-search-status")
        status_label.update("[italic green]Fetching related items...[/italic green]")
        
        self.preloaded_entities = []
        self.preloaded_metrics = []
        self.preloaded_series = []
        self.large_search_space = False
        self.inspector_prefetching = True
        
        try:
            if isinstance(resource, Entity):
                relations = await asyncio.to_thread(self.client.get_entity_relations, resource.id, limit=201)
                metrics = await asyncio.to_thread(self.client.search_metrics, "", entity=resource.id, limit=201)
                
                self.preloaded_entities = relations
                self.preloaded_metrics = metrics
                
                if len(relations) > 200 or len(metrics) > 200:
                    self.large_search_space = True
                    status_label.update("[yellow]Large search space (>200 items); server search active[/yellow]")
                else:
                    status_label.update("")
                    
            elif isinstance(resource, Metric):
                series = await asyncio.to_thread(self.client.get_metric_series, resource.id, limit=201)
                entities = await asyncio.to_thread(self.client.search_entities, "", metric=resource.id, limit=201)
                
                self.preloaded_series = series
                self.preloaded_entities = entities
                
                if len(series) > 200 or len(entities) > 200:
                    self.large_search_space = True
                    status_label.update("[yellow]Large search space (>200 items); server search active[/yellow]")
                else:
                    status_label.update("")
            elif isinstance(resource, Series):
                # Leaf level Series details
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
                self.inspector_search_task = asyncio.create_task(self._do_inspector_search(current_query))
            else:
                self._update_inspector_results("", initial=True)
            
    @on(Input.Changed, "#inspector-search-input")
    def on_inspector_search_changed(self, event: Input.Changed) -> None:
        """Trigger search when input in inspector changes."""
        if self.inspector_prefetching:
            return
        if self.inspector_search_task:
            self.inspector_search_task.cancel()
        self.inspector_search_task = asyncio.create_task(self._do_inspector_search(event.value))
        
    async def _do_inspector_search(self, query: str) -> None:
        try:
            await asyncio.sleep(0.3)
            resource = self.current_inspected_resource
            if not resource:
                return
                
            if self.large_search_space and len(query) >= 2:
                self.query_one("#inspector-search-status").update("[italic green]Searching server...[/italic green]")
                if isinstance(resource, Entity):
                    # Search metrics for this entity
                    metrics = await asyncio.to_thread(self.client.search_metrics, query, entity=resource.id, limit=50)
                    local_relations = [
                        r for r in self.preloaded_entities
                        if query.lower() in (getattr(r, "id", "") or "").lower() or query.lower() in r.id.lower()
                    ]
                    self._update_inspector_list(local_relations, metrics)
                elif isinstance(resource, Metric):
                    # Search entities for this metric
                    entities = await asyncio.to_thread(self.client.search_entities, query, metric=resource.id, limit=50)
                    local_series = [
                        s for s in self.preloaded_series
                        if query.lower() in (getattr(s, "label", "") or "").lower() or query.lower() in s.id.lower()
                    ]
                    self._update_inspector_list(entities, local_series)
                self.query_one("#inspector-search-status").update("[yellow]Large search space (>200 items); server search active[/yellow]")
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
            if isinstance(e, EntityRelationship):
                label = getattr(e, "target_label", getattr(e, "target_name", "")) or ""
                item_id = e.id
            else:
                label = getattr(e, "label", getattr(e, "name", "")) or ""
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
        """Move focus to results list when Enter is pressed in search input."""
        self.query_one("#inspector-results-list", ListView).focus()
    @on(ListView.Selected, "#inspector-results-list")
    def on_inspector_item_selected(self, event: ListView.Selected) -> None:
        self.add_inspector_item_to_basket(event.item.resource)
    @work(exclusive=True)
    async def add_inspector_item_to_basket(self, item: Any) -> None:
        try:
            if isinstance(item, EntityRelationship):
                resource = await asyncio.to_thread(self.client.get_entity, item.id)
            elif isinstance(item, (Series, Entity, Metric)):
                resource = item
            else:
                return

            if not self._add_resource_to_session(resource):
                self.notify(f"{resource.id} is already in basket", severity="warning")
                return

            self.basket.append(resource)
            self._rebuild_basket_list()
            self.notify(f"Added {resource.id} to basket")
            self._update_stats()
        except Exception as e:
            self.notify(f"Error adding to basket: {e}", severity="error")


class ExplorerScreen(Screen):
    """The result viewer (Tab 2)."""

    def __init__(self, client: JSTDataClient, session: Session) -> None:
        super().__init__()
        self.client = client
        self.session = session
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("EXPLORER // DATA_VIEW", classes="pane-header")
        with Horizontal(id="explorer-body"):
            yield DataTable(id="explorer-table")
            with Vertical(id="explorer-sidebar", classes="pane-container"):
                yield Label("EXPORT // PYTHON_CODE", classes="sidebar-header")
                yield Static(id="python-code-display", classes="code-display")
                yield Button("COPY PYTHON", id="copy-python-btn", variant="primary")
                
                yield Label("EXPORT // CLI_COMMAND", classes="sidebar-header")
                yield Static(id="cli-command-display", classes="code-display")
                yield Button("COPY COMMAND", id="copy-cli-btn", variant="primary")
                
                yield Label("EXPORT // CSV", classes="sidebar-header")
                yield Button("EXPORT TO CSV", id="export-csv-btn", variant="primary")
                
        with Horizontal(id="explorer-footer"):
            yield Label("RUNNING", id="explorer-status")
            yield Label("ROWS: 0", id="explorer-count")
            yield Label("BACK TO WORKSPACE (ESC)", id="explorer-hint")
        yield Footer()

    def on_mount(self) -> None:
        self.python_code = self.session.to_python()
        self.cli_command = self.session.to_cli()
        self.query_one("#python-code-display", Static).update(self.python_code)
        self.query_one("#cli-command-display", Static).update(self.cli_command)
        self.run_query()

    @on(Button.Pressed, "#copy-python-btn")
    def copy_python_code(self) -> None:
        copy_to_clipboard(self.app, self.python_code)
        self.notify("Python snippet copied to clipboard!")

    @on(Button.Pressed, "#copy-cli-btn")
    def copy_cli_command(self) -> None:
        copy_to_clipboard(self.app, self.cli_command)
        self.notify("CLI command copied to clipboard!")

    @on(Button.Pressed, "#export-csv-btn")
    def export_csv(self) -> None:
        try:
            path = self.session.to_csv(self.client, order_by="desc")
            self.notify(f"Data successfully exported to {path}")
        except Exception as e:
            self.notify(f"Failed to export CSV: {e}", severity="error")

    @work(exclusive=True)
    async def run_query(self) -> None:
        table = self.query_one("#explorer-table", DataTable)
        table.clear(columns=True)
        table.add_columns("DATE", "LABEL", "VALUE", "UNITS", "SOURCE")

        try:
            time_series_list = await asyncio.to_thread(
                self.session.execute, self.client, order_by="desc"
            )

            rcount = 0
            if not time_series_list:
                self.notify("No results found", severity="warning")
                self.query_one("#explorer-status").update("NO RESULTS")
            else:
                for t in time_series_list:
                    for o in t.observations:
                        table.add_row(
                            o.observation_timestamp.strftime("%Y-%m-%d"),
                            t.series.label,
                            f"{o.value:,.4f}",
                            t.series.units,
                            t.series.source,
                        )
                        rcount += 1
                self.query_one("#explorer-status").update("READY")

            self.query_one("#explorer-count").update(f"ROWS: {rcount}")
        except Exception as e:
            self.notify(f"Query error: {e}", severity="error")
            self.query_one("#explorer-status").update("ERROR")



class HelpScreen(ModalScreen):
    """A modal screen showing keybindings help."""
    
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #help-container {
        width: 50;
        height: auto;
        border: thick #4ade80;
        background: #111111;
        padding: 1 2;
    }

    #help-title {
        text-style: bold;
        color: #4ade80;
        margin-bottom: 1;
        text-align: center;
    }

    .key-row {
        height: 1;
        margin-bottom: 0;
    }

    .key-col {
        color: #4ade80;
        text-style: bold;
        width: 15;
    }

    .desc-col {
        color: #e0e0e0;
        width: 30;
    }

    #help-close-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Dismiss"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("KEYBINDINGS // HELPMENU", id="help-title")
            
            yield Horizontal(Label("q / ctrl+c", classes="key-col"), Label("Quit application", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("ctrl+e", classes="key-col"), Label("Execute query (reliable)", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("shift+enter", classes="key-col"), Label("Execute query (if supported)", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("i", classes="key-col"), Label("Inspect selected item", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("escape", classes="key-col"), Label("Back to workspace", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("enter (search)", classes="key-col"), Label("Focus search results", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("enter (results)", classes="key-col"), Label("Add item to basket", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("backspace", classes="key-col"), Label("Remove item from basket", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("j / ↓", classes="key-col"), Label("Move highlight down", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("k / ↑", classes="key-col"), Label("Move highlight up", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("?", classes="key-col"), Label("Show this help menu", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("s", classes="key-col"), Label("Save session (prompt)", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("o", classes="key-col"), Label("Offramp (Python / CLI / write)", classes="desc-col"), classes="key-row")
            yield Horizontal(Label("l", classes="key-col"), Label("Load session", classes="desc-col"), classes="key-row")

            yield Button("CLOSE (ESC)", variant="error", id="help-close-btn")

    def action_dismiss(self) -> None:
        self.dismiss()


class SessionModal(ModalScreen[str | None]):
    """Modal for saving/loading session files."""
    
    DEFAULT_CSS = """
    SessionModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #session-container {
        width: 60;
        height: auto;
        border: thick #4ade80;
        background: #111111;
        padding: 1 2;
    }

    #session-title {
        text-style: bold;
        color: #4ade80;
        margin-bottom: 1;
        text-align: center;
    }

    #session-input {
        width: 1fr;
        margin: 1 0;
    }

    #session-btn {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Cancel"),
        ("enter", "submit", "Submit"),
    ]

    def __init__(self, title: str, placeholder: str, default: str = ""):
        super().__init__()
        self.title = title
        self.placeholder = placeholder
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="session-container"):
            yield Label(self.title, id="session-title")
            yield Input(placeholder=self.placeholder, id="session-input", value=self.default)
            yield Button("OK", variant="primary", id="session-btn")

    @on(Button.Pressed, "#session-btn")
    def submit_button(self) -> None:
        self.action_submit()

    def action_submit(self) -> None:
        input_widget = self.query_one("#session-input", Input)
        if input_widget.value.strip():
            self.dismiss(input_widget.value.strip())

    def action_dismiss(self) -> None:
        self.dismiss(None)

# --- Main App ---

class JSTDataApp(App):
    """Jefferson Street Research OS - TUI v2."""

    CSS = """
    Screen {
        background: #0a0a0a;
        color: #e0e0e0;
    }

    /* Layout Containers */
    #workspace-body {
        height: 1fr;
    }
    #left-column {
        width: 65%;
    }
    #right-column {
        width: 35%;
        border-left: solid #333;
    }

    .pane-container {
        border: solid #222;
        background: #0f0f0f;
    }
    #results-pane { height: 60%; }
    #inspector-pane { height: 40%; border-top: solid #333; }

    /* Headers */
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

    /* Columns */
    .col-name { width: 55%; }
    .col-id   { width: 25%; }
    .col-src  { width: 10%; }
    .col-type { width: 10%; }

    /* List Items */
    SearchResultRow {
        padding: 0 1;
        height: 1;
    }
    SearchResultRow:focus {
        background: #1a3a1a;
        color: #4ade80;
    }

    /* Basket */
    #basket-list {
        height: 1fr;
    }
    BasketHeader {
        background: #1a1a1a;
        padding: 0 1;
        height: 1;
    }
    BasketHeader .basket-header-label {
        color: #4ade80 !important;
        text-style: bold;
    }
    BasketItem {
        padding: 1 1;
        border-bottom: solid #222;
        height: 4;
    }
    .basket-item-name { color: #fff; }
    .basket-item-subtext { color: #666; }
    .remove-btn { min-width: 3; height: 1; margin-top: 1; }

    /* Summary */
    #basket-summary {
        height: 6;
        padding: 1 2;
        background: #151515;
        border-top: solid #333;
    }
    .stat-label { color: #888; }
    .stat-value { color: #4ade80; text-style: bold; margin-bottom: 1; }

    /* CMD Bar */
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
    #status-labels {
        width: auto;
        padding: 0 2;
    }
    .status-item {
        margin-left: 2;
        color: #888;
    }

    /* Inspector Interactive View CSS */
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
    .insp-col-type { width: 12; color: #888; }
    .insp-col-name { width: 25; color: #fff; }
    .insp-col-id   { width: 15; color: #4ade80; }
    InspectorResultRow {
        padding: 0 1;
        height: 1;
    }
    InspectorResultRow:focus {
        background: #1a3a1a;
        color: #4ade80;
    }

    /* Explorer */
    #explorer-body {
        height: 1fr;
    }
    #explorer-table {
        width: 65%;
        height: 100%;
    }
    #explorer-sidebar {
        width: 35%;
        height: 100%;
        border-left: solid #333;
        padding: 1 2;
        background: #0f0f0f;
    }
    .sidebar-header {
        background: #1a1a1a;
        color: #4ade80;
        padding: 0 1;
        text-style: bold;
        height: 1;
        margin-top: 1;
        margin-bottom: 0;
    }
    .code-display {
        background: #050505;
        color: #f8f8f2;
        padding: 1 1;
        height: 8;
        border: solid #222;
        margin-bottom: 1;
        overflow-y: scroll;
    }
    #explorer-sidebar Button {
        margin-bottom: 1;
        width: 100%;
    }
    #explorer-footer {
        height: 1;
        background: #111;
        color: #4ade80;
        padding: 0 2;
    }
    """


    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "back", "Back"),
        Binding("question_mark", "show_help", "Show Keybindings", key_display="?"),
        Binding("s", "save_session", "Save"),
        Binding("o", "offramp", "Offramp"),
    ]

    def __init__(
        self,
        client: JSTDataClient,
        session_path: str | None = None,
        output_path: str | None = None,
        workflow_id: str = "console",
    ) -> None:
        super().__init__()
        self.client = client
        self.workflow_id = workflow_id
        self.output_path = output_path or default_session_path(workflow_id)
        self.session = load_session_or_empty(session_path)
        self.basket: list[Resource] = []

    def on_mount(self) -> None:
        self.push_screen(
            WorkspaceScreen(
                client=self.client,
                session=self.session,
                basket=self.basket,
            )
        )

    def action_save_session(self) -> None:
        """User-initiated session write with unique default path."""
        self.push_screen(
            SessionModal(
                "Save session to file:",
                self.output_path,
                default=self.output_path,
            ),
            self._on_save_session_path,
        )

    def _on_save_session_path(self, filepath: str | None) -> None:
        if not filepath:
            return
        try:
            self.session.save(filepath)
            self.output_path = filepath
            self.notify(f"Session saved to {filepath}")
        except Exception as e:
            self.notify(f"Failed to save session: {e}", severity="error")

    def action_offramp(self) -> None:
        """Shared offramp: copy Python/CLI or write session."""
        self.push_screen(OfframpModal(self.session, default_path=self.output_path))

    def action_back(self) -> None:
        """Return to workspace or leave inspector focus."""
        if isinstance(self.screen, ExplorerScreen):
            self.pop_screen()
        elif isinstance(self.screen, WorkspaceScreen):
            focused = self.focused
            if focused and focused.id in ("inspector-search-input", "inspector-results-list"):
                self.screen.query_one("#search-input", Input).focus()

    def action_show_help(self) -> None:
        """Show the keybindings help screen."""
        self.push_screen(HelpScreen())




if __name__ == "__main__":
    client = JSTDataClient()
    app = JSTDataApp(client)
    app.run()
