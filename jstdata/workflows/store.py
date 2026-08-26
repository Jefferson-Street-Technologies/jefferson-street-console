"""Persisted workflows: named pipelines saved as YAML under ``~/.jstdata/workflows``.

Steps are the catalog units (``jst steps`` / ``jst run``). Workflows are
user-saved compositions of those steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from ..client import APP_DIR
from .base import PipelineError, ResolvedStep, resolve_pipeline

WORKFLOWS_DIR = APP_DIR / "workflows"
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class WorkflowStoreError(ValueError):
    """Invalid workflow id, missing file, or corrupt YAML."""


@dataclass(frozen=True)
class SavedStep:
    """One step in a saved workflow (id + seed args)."""

    id: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id}
        if self.args:
            data["args"] = dict(self.args)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SavedStep:
        if not isinstance(data, dict) or "id" not in data:
            raise WorkflowStoreError("Each step must be a mapping with an 'id'.")
        args = data.get("args") or {}
        if not isinstance(args, dict):
            raise WorkflowStoreError(f"Step {data['id']!r} args must be a mapping.")
        return cls(id=str(data["id"]), args=dict(args))


@dataclass(frozen=True)
class SavedWorkflow:
    """User-saved pipeline stored on disk."""

    id: str
    description: str = ""
    steps: tuple[SavedStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description or "",
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SavedWorkflow:
        if not isinstance(data, dict):
            raise WorkflowStoreError("Workflow file must be a YAML mapping.")
        wid = data.get("id")
        if not wid or not isinstance(wid, str):
            raise WorkflowStoreError("Workflow is missing a string 'id'.")
        validate_workflow_id(wid)
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise WorkflowStoreError(f"Workflow {wid!r} must list at least one step.")
        steps = tuple(SavedStep.from_dict(s) for s in raw_steps)
        description = data.get("description") or ""
        if not isinstance(description, str):
            raise WorkflowStoreError("Workflow 'description' must be a string.")
        return cls(id=wid, description=description, steps=steps)

    @classmethod
    def from_resolved(
        cls,
        workflow_id: str,
        description: str,
        resolved: list[ResolvedStep],
    ) -> SavedWorkflow:
        validate_workflow_id(workflow_id)
        if not resolved:
            raise WorkflowStoreError("Pipeline is empty.")
        steps = tuple(
            SavedStep(id=r.spec.id, args=dict(r.kwargs)) for r in resolved
        )
        return cls(id=workflow_id, description=description or "", steps=steps)


def validate_workflow_id(workflow_id: str) -> str:
    """Require a lowercase slug: ``gdp-rank``, not ``GDP Rank``."""
    if not _SLUG_RE.match(workflow_id):
        raise WorkflowStoreError(
            f"Invalid workflow id {workflow_id!r}. "
            "Use a slug like 'gdp-rank' (lowercase letters, digits, hyphens)."
        )
    return workflow_id


def workflow_path(workflow_id: str, *, root: Optional[Path] = None) -> Path:
    validate_workflow_id(workflow_id)
    base = root if root is not None else WORKFLOWS_DIR
    return base / f"{workflow_id}.yaml"


def ensure_workflows_dir(*, root: Optional[Path] = None) -> Path:
    base = root if root is not None else WORKFLOWS_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def workflow_exists(workflow_id: str, *, root: Optional[Path] = None) -> bool:
    return workflow_path(workflow_id, root=root).is_file()


def save_workflow(
    workflow: SavedWorkflow,
    *,
    root: Optional[Path] = None,
) -> Path:
    """Write workflow YAML; overwrites if the file already exists."""
    ensure_workflows_dir(root=root)
    path = workflow_path(workflow.id, root=root)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            workflow.to_dict(),
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return path


def load_workflow(
    workflow_id: str,
    *,
    root: Optional[Path] = None,
) -> SavedWorkflow:
    path = workflow_path(workflow_id, root=root)
    if not path.is_file():
        raise WorkflowStoreError(f"No workflow named {workflow_id!r}.")
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise WorkflowStoreError(f"Could not parse {path}: {exc}") from exc
    workflow = SavedWorkflow.from_dict(data or {})
    if workflow.id != workflow_id:
        raise WorkflowStoreError(
            f"Workflow file {path.name} has id {workflow.id!r}, "
            f"expected {workflow_id!r}."
        )
    return workflow


def delete_workflow(workflow_id: str, *, root: Optional[Path] = None) -> None:
    path = workflow_path(workflow_id, root=root)
    if not path.is_file():
        raise WorkflowStoreError(f"No workflow named {workflow_id!r}.")
    path.unlink()


def list_saved_workflows(*, root: Optional[Path] = None) -> list[SavedWorkflow]:
    base = root if root is not None else WORKFLOWS_DIR
    if not base.is_dir():
        return []
    out: list[SavedWorkflow] = []
    for path in sorted(base.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            out.append(SavedWorkflow.from_dict(data or {}))
        except (WorkflowStoreError, yaml.YAMLError, OSError):
            # Skip corrupt files in listings; load/run still error loudly.
            continue
    return out


def workflow_to_tokens(workflow: SavedWorkflow) -> list[str]:
    """Rebuild ``jst run``-style argv from structured YAML (no raw argv stored)."""
    tokens: list[str] = []
    for i, step in enumerate(workflow.steps):
        if i:
            tokens.append(":")
        tokens.append(step.id)
        for name, value in step.args.items():
            flag = "--" + str(name).replace("_", "-")
            if isinstance(value, bool):
                if value:
                    tokens.append(flag)
                continue
            tokens.append(flag)
            tokens.append(str(value))
    return tokens


def format_pipeline(workflow: SavedWorkflow) -> str:
    """One-line pipeline summary for ``jst workflows ls``."""
    return " ".join(workflow_to_tokens(workflow))


def resolve_saved_workflow(workflow: SavedWorkflow) -> list[ResolvedStep]:
    """Validate a saved workflow against the live step catalog (no UI)."""
    try:
        return resolve_pipeline(workflow_to_tokens(workflow))
    except KeyError as exc:
        raise PipelineError(str(exc)) from exc


def create_workflow_from_tokens(
    workflow_id: str,
    description: str,
    tokens: list[str],
) -> SavedWorkflow:
    """Parse/validate pipeline tokens, then build a SavedWorkflow."""
    validate_workflow_id(workflow_id)
    resolved = resolve_pipeline(tokens)
    return SavedWorkflow.from_resolved(workflow_id, description, resolved)
