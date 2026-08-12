"""Console workflow — general-purpose session editor TUI."""

from __future__ import annotations

from typing import Optional

from ..client import JSTDataClient
from .base import WorkflowSpec, register


def launch_console(
    client: JSTDataClient,
    session_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """Launch the console workflow TUI."""
    from ..tui import JSTDataApp

    app = JSTDataApp(
        client,
        session_path=session_path,
        output_path=output_path,
        workflow_id="console",
    )
    app.run()


CONSOLE = register(
    WorkflowSpec(
        id="console",
        name="Console",
        description="General-purpose session editor",
        launch=launch_console,
    )
)
