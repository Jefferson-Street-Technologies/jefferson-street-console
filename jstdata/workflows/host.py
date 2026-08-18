"""Workflow host: shared pipeline runtime and universal modals wiring."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label

from ..client import JSTDataClient
from .base import (
    ResolvedStep,
    default_session_path,
    hydrate_labels,
    load_session_or_empty,
)
from .export import ExportModal
from .find import FindModal
from .session_manager import SessionManagerModal


class HelpScreen(ModalScreen):
    """Step-specific keybindings from the current StepSpec."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #help-container {
        width: 60;
        height: auto;
        max-height: 90%;
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

    #help-note {
        color: #888;
        margin-bottom: 1;
        text-align: center;
    }

    .key-row {
        height: auto;
        margin-bottom: 0;
    }

    .key-col {
        color: #4ade80;
        text-style: bold;
        width: 16;
    }

    .desc-col {
        color: #e0e0e0;
        width: 1fr;
    }

    #help-footer {
        color: #888;
        margin-top: 1;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close", show=False),
    ]

    def __init__(self, step_name: str, bindings: list) -> None:
        super().__init__()
        self.step_name = step_name
        self.step_bindings = bindings

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label(f"{self.step_name.upper()} // KEYBINDINGS", id="help-title")
            yield Label(
                "Universal keys stay in the status bar (s/f/e/n/p/q).",
                id="help-note",
            )
            if not self.step_bindings:
                yield Label("(no step-specific bindings)", classes="desc-col")
            else:
                for b in self.step_bindings:
                    if not getattr(b, "show_in_help", True):
                        continue
                    yield Horizontal(
                        Label(b.key, classes="key-col"),
                        Label(b.description, classes="desc-col"),
                        classes="key-row",
                    )
            yield Label("[bold]esc[/bold] / [bold]?[/bold] close", id="help-footer", markup=True)

    def action_dismiss(self) -> None:
        self.dismiss()


class WorkflowHost(App):
    """One-process host for a pipeline of steps sharing a Session."""

    CSS = """
    Screen {
        background: #0a0a0a;
        color: #e0e0e0;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "back", "Back"),
        Binding("question_mark", "show_help", "Step help", key_display="?"),
        Binding("s", "session", "Session"),
        Binding("f", "find", "Find"),
        Binding("e", "export", "Export"),
        Binding("n", "next_step", "Next"),
        Binding("p", "prev_step", "Prev"),
    ]

    def __init__(
        self,
        client: JSTDataClient,
        steps: list[ResolvedStep],
        session_path: str | None = None,
        output_path: str | None = None,
    ) -> None:
        super().__init__()
        if not steps:
            raise ValueError("WorkflowHost requires at least one step")
        self.client = client
        self.steps = steps
        self.step_index = 0
        prefix = "-".join(s.spec.id for s in steps)
        self.output_path = output_path or default_session_path(prefix)
        self.session = load_session_or_empty(session_path)
        self.labels: dict[str, str] = {}
        hydrate_labels(self.client, self.session, self.labels)

    def remember_label(self, resource_id: str, label: str) -> None:
        """Cache a display label for UI (session remains source of truth)."""
        self.labels[resource_id] = label or resource_id

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def current_step_id(self) -> str:
        return self.steps[self.step_index].spec.id

    @property
    def current_step_spec(self):
        return self.steps[self.step_index].spec

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Let printable host keys fall through to focused Inputs (search, path, etc.).
        if action in {"session", "find", "export", "next_step", "prev_step", "show_help"}:
            if isinstance(self.focused, Input):
                return False
        return True

    def on_mount(self) -> None:
        self._push_current_step()

    def _make_current_screen(self):
        resolved = self.steps[self.step_index]
        return resolved.spec.create_screen(
            self.client,
            self.session,
            **resolved.kwargs,
        )

    def _push_current_step(self) -> None:
        self.push_screen(self._make_current_screen())

    def _pop_overlays(self) -> None:
        """Pop modals until a single step screen remains."""
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def action_next_step(self) -> None:
        if self.step_index >= len(self.steps) - 1:
            self.notify("Last step in the pipeline", severity="warning")
            return
        self._pop_overlays()
        self.step_index += 1
        self.switch_screen(self._make_current_screen())

    def action_prev_step(self) -> None:
        if self.step_index <= 0:
            self.notify("First step in the pipeline", severity="warning")
            return
        self._pop_overlays()
        self.step_index -= 1
        self.switch_screen(self._make_current_screen())

    def action_session(self) -> None:
        """Shared session manager: remove / inspect staged resources."""
        self.push_screen(
            SessionManagerModal(self.client, self.session, self.labels)
        )

    def action_find(self) -> None:
        """Shared find: search catalog and add resources to the session."""
        self.push_screen(FindModal(self.client, self.session))

    def action_export(self) -> None:
        """Shared export: copy Python/CLI or write session file."""
        self.push_screen(ExportModal(self.session, default_path=self.output_path))

    def action_inspect(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_inspect"):
            screen.action_inspect()

    def action_back(self) -> None:
        """Leave step-local filter / inspector focus when applicable."""
        focused = self.focused
        screen = self.screen
        if getattr(focused, "id", None) == "metrics-filter" and hasattr(
            screen, "action_leave_filter"
        ):
            screen.action_leave_filter()
            return
        if focused and getattr(focused, "id", None) in (
            "inspector-search-input",
            "inspector-results-list",
        ):
            try:
                screen.query_one("#search-input", Input).focus()
            except Exception:
                pass

    def action_show_help(self) -> None:
        """Show step-specific keybindings from the current StepSpec."""
        spec = self.current_step_spec
        self.push_screen(HelpScreen(spec.name, list(spec.bindings)))


# Back-compat alias
JSTDataApp = WorkflowHost
