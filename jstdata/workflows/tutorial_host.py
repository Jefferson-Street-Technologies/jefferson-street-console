"""Tutorial host: WorkflowHost plus a persistent coach bar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, Static

from .export import ExportModal
from .host import WorkflowHost
from .tutorial import TutorialCoach, TutorialCoachBar


class CoachBarWidget(Static):
    """Docked instruction strip shown for the whole tutorial run."""

    DEFAULT_CSS = """
    CoachBarWidget {
        dock: top;
        height: auto;
        min-height: 4;
        max-height: 8;
        background: #1a1a2e;
        border-bottom: thick #38bdf8;
        padding: 0 1;
    }

    #coach-header {
        color: #38bdf8;
        text-style: bold;
        height: 1;
    }

    #coach-body {
        color: #e0e0e0;
        height: auto;
        padding-bottom: 1;
    }
    """

    def __init__(self, header: str = "", body: str = "") -> None:
        super().__init__()
        self._header = header
        self._body = body

    def compose(self) -> ComposeResult:
        yield Label(self._header, id="coach-header")
        yield Static(self._body, id="coach-body")

    def update_coach(self, header: str, body: str) -> None:
        if not self.is_mounted:
            self._header = header
            self._body = body
            return
        self.query_one("#coach-header", Label).update(header)
        self.query_one("#coach-body", Static).update(body)


class TutorialHost(WorkflowHost):
    """WorkflowHost with phased on-screen guidance for the bundled tutorial."""

    def __init__(
        self,
        client,
        steps,
        coach: TutorialCoach,
        session_path: str | None = None,
        output_path: str | None = None,
    ) -> None:
        super().__init__(client, steps, session_path=session_path, output_path=output_path)
        self.coach = coach
        self._coach_bar: CoachBarWidget | None = None

    def on_mount(self) -> None:
        self.coach.maybe_advance(self.session, self.step_index, None)
        self.set_interval(0.25, self._poll_coach)
        self._push_current_step()

    def _coach_text(self) -> tuple[str, str]:
        phase = self.coach.current_phase
        if phase is None:
            return (
                "TUTORIAL · complete",
                "Tutorial complete. Press q to quit.",
            )
        return (
            TutorialCoachBar.format_header(self.coach.progress_label),
            phase.text,
        )

    def _poll_coach(self) -> None:
        if self.coach.maybe_advance(self.session, self.step_index, None):
            self._refresh_coach()

    def _refresh_coach(self) -> None:
        if self._coach_bar is None or not self._coach_bar.is_mounted:
            return
        header, body = self._coach_text()
        self._coach_bar.update_coach(header, body)

    def _push_current_step(self) -> None:
        self.push_screen(self._make_current_screen())
        self.call_after_refresh(self._mount_coach_on_active_screen)

    def _mount_coach_on_active_screen(self) -> None:
        """Mount coach on the active step screen (App-level mounts sit behind Screens)."""
        screen = self.screen
        if not isinstance(screen, Screen):
            return
        if self._coach_bar is not None and self._coach_bar.is_mounted:
            self._coach_bar.remove()
        header, body = self._coach_text()
        self._coach_bar = CoachBarWidget(header, body)
        screen.mount(self._coach_bar)

    def _after_step_change(self) -> None:
        self.call_after_refresh(self._mount_coach_on_active_screen)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        phase = self.coach.current_phase
        if (
            action == "next_step"
            and phase is not None
            and phase.until.get("action") == "next_step"
        ):
            return True
        return super().check_action(action, parameters)

    def action_next_step(self) -> None:
        phase = self.coach.current_phase
        if phase is not None and not self.coach.is_complete:
            if phase.until.get("action") != "next_step":
                if self.coach.gate_progress(self.session, self.step_index):
                    self.notify(
                        "Finish the current tutorial step first.",
                        severity="warning",
                    )
                    return
        if self.step_index >= len(self.steps) - 1:
            self.notify("Last step in the pipeline", severity="warning")
            return
        advanced = self.coach.maybe_advance(
            self.session, self.step_index, "next_step"
        )
        self._pop_overlays()
        self.step_index += 1
        self.switch_screen(self._make_current_screen())
        self._after_step_change()
        if advanced:
            self._refresh_coach()

    def action_prev_step(self) -> None:
        if self.step_index <= 0:
            self.notify("First step in the pipeline", severity="warning")
            return
        self._pop_overlays()
        self.step_index -= 1
        self.switch_screen(self._make_current_screen())
        self._after_step_change()

    def action_session(self) -> None:
        super().action_session()
        if self.coach.maybe_advance(self.session, self.step_index, "open_session"):
            self._refresh_coach()

    def action_export(self) -> None:
        self.push_screen(
            ExportModal(
                self.session,
                default_path=self.output_path,
                on_write=self._on_tutorial_session_written,
            )
        )

    def _on_tutorial_session_written(self, path: str) -> None:
        if self.coach.maybe_advance(self.session, self.step_index, "session_written"):
            self._refresh_coach()
            self.notify(f"Tutorial complete — session saved to {path}")
