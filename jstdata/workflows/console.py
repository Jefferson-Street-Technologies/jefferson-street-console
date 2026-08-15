"""Console step — general-purpose session editor TUI."""

from __future__ import annotations

from .base import StepBinding, StepSpec, register


def create_console_screen(client, session, **kwargs):
    from ..tui import WorkspaceScreen

    return WorkspaceScreen(client, session)


CONSOLE = register(
    StepSpec(
        id="console",
        name="Console",
        description=(
            "General-purpose session editor. Search metrics, entities, and series; "
            "stage resources; inspect related metadata."
        ),
        create_screen=create_console_screen,
        arguments=(),
        bindings=(
            StepBinding("i", "inspect", "Inspect related resources for highlighted result"),
            StepBinding("enter", "submit", "Focus results (from search) / add to session (from results)"),
            StepBinding("j / ↓", "cursor_down", "Move highlight down"),
            StepBinding("k / ↑", "cursor_up", "Move highlight up"),
            StepBinding("escape", "back", "Leave inspector focus"),
        ),
        example="jst run console",
    )
)
