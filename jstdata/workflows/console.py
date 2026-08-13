"""Console step — general-purpose session editor TUI."""

from __future__ import annotations

from .base import StepSpec, register


def create_console_screen(client, session, basket, **kwargs):
    from ..tui import WorkspaceScreen

    return WorkspaceScreen(client, session, basket)


CONSOLE = register(
    StepSpec(
        id="console",
        name="Console",
        description="General-purpose session editor. Search metrics, entities, and series; stage a basket; inspect metadata.",
        create_screen=create_console_screen,
        arguments=(),
        example="jst run console",
    )
)
