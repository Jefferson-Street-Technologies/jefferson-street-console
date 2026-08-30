"""Interactive tutorial coach for the bundled ``tutorial`` workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any, Callable, Mapping, Optional

import yaml

from ..client import JSTDataClient
from ..session import Session
from .base import default_session_path
from .export import ExportModal
from .store import (
    TUTORIAL_WORKFLOW_ID,
    load_workflow,
    resolve_saved_workflow,
)

_SCRIPT_PATH = "tutorial_script.yaml"


@dataclass(frozen=True)
class TutorialPhase:
    text: str
    step_index: Optional[int] = None
    until: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TutorialPhase:
        until = data.get("until") or {}
        if not isinstance(until, dict):
            raise ValueError("Tutorial phase 'until' must be a mapping.")
        step_index = data.get("step_index")
        if step_index is not None:
            step_index = int(step_index)
        return cls(
            text=str(data.get("text") or "").strip(),
            step_index=step_index,
            until=until,
        )


@dataclass
class TutorialCoach:
    phases: tuple[TutorialPhase, ...]
    phase_index: int = 0

    @classmethod
    def load(cls) -> TutorialCoach:
        raw = files("jstdata.workflows.bundled").joinpath(_SCRIPT_PATH).read_text(
            encoding="utf-8"
        )
        data = yaml.safe_load(raw) or {}
        items = data.get("phases") or []
        if not items:
            raise ValueError("Tutorial script has no phases.")
        return cls(phases=tuple(TutorialPhase.from_dict(p) for p in items))

    @property
    def is_complete(self) -> bool:
        return self.phase_index >= len(self.phases)

    @property
    def current_phase(self) -> Optional[TutorialPhase]:
        if self.is_complete:
            return None
        return self.phases[self.phase_index]

    @property
    def progress_label(self) -> str:
        total = len(self.phases)
        current = min(self.phase_index + 1, total)
        return f"Step {current} / {total}"

    def _phase_matches(
        self,
        phase: TutorialPhase,
        session: Session,
        step_index: int,
        action: Optional[str],
    ) -> bool:
        until = phase.until or {}
        if until.get("done"):
            return False
        if until.get("auto"):
            return True
        if phase.step_index is not None and phase.step_index != step_index:
            return False
        if "session_entity_count" in until:
            needed = int(until["session_entity_count"])
            return len(session.entity) >= needed
        if "session_metric_count" in until:
            needed = int(until["session_metric_count"])
            return len(session.metric) >= needed
        if "action" in until:
            return action == until["action"]
        return False

    def maybe_advance(
        self,
        session: Session,
        step_index: int,
        action: Optional[str] = None,
    ) -> bool:
        """Advance when the current phase's completion rule is satisfied."""
        if self.is_complete:
            return False
        phase = self.current_phase
        assert phase is not None
        if not self._phase_matches(phase, session, step_index, action):
            return False
        self.phase_index += 1
        return True

    def gate_progress(self, session: Session, step_index: int) -> bool:
        """True when navigation should be blocked (incomplete count-based phase)."""
        phase = self.current_phase
        if phase is None or self.is_complete:
            return False
        if phase.until.get("action") == "next_step":
            return False
        if phase.step_index is not None and phase.step_index != step_index:
            return False
        until = phase.until or {}
        if "session_entity_count" in until:
            return len(session.entity) < int(until["session_entity_count"])
        if "session_metric_count" in until:
            return len(session.metric) < int(until["session_metric_count"])
        return False


class TutorialCoachBar:
    """Mixin-friendly helper; actual widget lives in tutorial_host.py."""

    @staticmethod
    def format_header(progress: str) -> str:
        return f"TUTORIAL · {progress}"


def run_tutorial(
    client: JSTDataClient,
    *,
    session_path: str | None = None,
    output_path: str | None = None,
) -> None:
    """Load bundled tutorial workflow and launch the coached host."""
    from .tutorial_host import TutorialHost

    workflow = load_workflow(TUTORIAL_WORKFLOW_ID)
    resolved = resolve_saved_workflow(workflow)
    coach = TutorialCoach.load()
    prefix = "-".join(s.spec.id for s in resolved)
    out = output_path or default_session_path(prefix)
    app = TutorialHost(
        client,
        resolved,
        coach,
        session_path=session_path,
        output_path=out,
    )
    app.run()
