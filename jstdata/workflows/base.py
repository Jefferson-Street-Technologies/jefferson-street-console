"""Workflow registry and shared launch helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Optional

from ..client import JSTDataClient
from ..session import Session

LaunchFn = Callable[[JSTDataClient, Optional[str], Optional[str]], None]


@dataclass(frozen=True)
class WorkflowSpec:
    """Metadata + launcher for a workflow TUI."""

    id: str
    name: str
    description: str
    launch: LaunchFn


def default_session_path(workflow_id: str = "session") -> str:
    """Unique-by-default session filename to avoid write conflicts."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{workflow_id}-{stamp}.json"


def apply_loaded_session(target: Session, loaded: Session) -> None:
    """Copy resource selectors and filters from ``loaded`` into ``target``."""
    target.metric = list(loaded.metric)
    target.entity = list(loaded.entity)
    target.series = list(loaded.series)
    target.frequency = loaded.frequency
    target.start_date = loaded.start_date
    target.end_date = loaded.end_date
    target.start_time = loaded.start_time
    target.end_time = loaded.end_time
    target.order_by = loaded.order_by


def load_session_or_empty(path: Optional[str]) -> Session:
    """Load a session from disk, or return an empty session."""
    if not path:
        return Session()
    return Session.load(path)


_REGISTRY: Dict[str, WorkflowSpec] = {}


def register(spec: WorkflowSpec) -> WorkflowSpec:
    """Register a workflow (idempotent by id)."""
    _REGISTRY[spec.id] = spec
    return spec


def get_workflow(workflow_id: str) -> WorkflowSpec:
    try:
        return _REGISTRY[workflow_id]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown workflow {workflow_id!r}. Available: {known}"
        ) from exc


def list_workflows() -> list[WorkflowSpec]:
    return [ _REGISTRY[k] for k in sorted(_REGISTRY) ]


def run_workflow(
    workflow_id: str,
    client: JSTDataClient,
    *,
    session_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """Launch a registered workflow TUI."""
    spec = get_workflow(workflow_id)
    spec.launch(client, session_path, output_path)
