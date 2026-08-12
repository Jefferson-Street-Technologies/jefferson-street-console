"""Analytical workflow TUIs.

Every workflow is a TUI that transforms a Session, launched via::

    jst workflow <name> [--session PATH] [--output PATH]

Shared across workflows:
- preload a session or start empty
- explicit save (never auto-write)
- identical offramp modal (Python / CLI / write session)
"""

from .base import (
    WorkflowSpec,
    default_session_path,
    get_workflow,
    list_workflows,
    run_workflow,
)
from . import console as _console  # noqa: F401  — registers console

__all__ = [
    "WorkflowSpec",
    "default_session_path",
    "get_workflow",
    "list_workflows",
    "run_workflow",
]
