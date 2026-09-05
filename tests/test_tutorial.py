"""Tests for the bundled tutorial workflow and coach."""

import pytest
from click.testing import CliRunner

import jstdata.workflows  # noqa: F401 — register steps
from jstdata.cli import cli
from jstdata.session import Session
from jstdata.workflows.store import (
    TUTORIAL_WORKFLOW_ID,
    WorkflowStoreError,
    delete_workflow,
    is_bundled_workflow,
    list_saved_workflows,
    load_bundled_workflow,
    load_workflow,
    resolve_saved_workflow,
)
from jstdata.workflows.tutorial import TutorialCoach


def test_bundled_tutorial_workflow_loads():
    wf = load_bundled_workflow(TUTORIAL_WORKFLOW_ID)
    assert wf.id == "tutorial"
    assert [s.id for s in wf.steps] == ["console", "discover"]
    assert wf.steps[0].args["taxonomy"] == "sec-central-index-key"
    assert wf.steps[0].args["resource_type"] == "entity"
    assert wf.steps[0].args["relation"] == [
        "classified_as:sic:7372",
        "classified_as:sic:5961",
        "classified_as:sic:3571",
    ]
    assert wf.steps[1].args["mode"] == "union"


def test_load_workflow_falls_back_to_bundled():
    wf = load_workflow(TUTORIAL_WORKFLOW_ID)
    assert wf.id == "tutorial"
    resolved = resolve_saved_workflow(wf)
    assert [r.spec.id for r in resolved] == ["console", "discover"]


def test_list_saved_workflows_includes_bundled(tmp_path, monkeypatch):
    monkeypatch.setattr("jstdata.workflows.store.WORKFLOWS_DIR", tmp_path)
    ids = [w.id for w in list_saved_workflows()]
    assert TUTORIAL_WORKFLOW_ID in ids


def test_delete_bundled_workflow_rejected():
    with pytest.raises(WorkflowStoreError, match="built-in"):
        delete_workflow(TUTORIAL_WORKFLOW_ID)


def test_coach_loads_and_advances():
    coach = TutorialCoach.load()
    session = Session()
    assert coach.maybe_advance(session, 0, None)  # welcome auto
    assert "Apple" in (coach.current_phase.text or "")

    session.add_entity("apple-inc")
    assert coach.maybe_advance(session, 0, None)
    assert "Microsoft" in (coach.current_phase.text or "")

    session.add_entity("microsoft-corp")
    session.add_entity("amazon-com-inc")
    assert coach.maybe_advance(session, 0, None)
    assert coach.current_phase.until.get("action") == "next_step"

    assert coach.maybe_advance(session, 0, "next_step")
    assert "Space" in (coach.current_phase.text or "")

    session.add_metric("revenue")
    assert coach.maybe_advance(session, 1, None)
    assert coach.current_phase.until.get("action") == "open_session"

    assert coach.maybe_advance(session, 1, "open_session")
    assert coach.current_phase.until.get("action") == "session_written"

    assert coach.maybe_advance(session, 1, "session_written")
    assert coach.current_phase.until.get("done")


def test_coach_advances_next_step_at_current_step_index():
    coach = TutorialCoach.load()
    session = Session()
    coach.maybe_advance(session, 0, None)  # welcome
    session.add_entity("apple-inc")
    coach.maybe_advance(session, 0, None)
    session.add_entity("microsoft-corp")
    session.add_entity("amazon-com-inc")
    coach.maybe_advance(session, 0, None)
    assert coach.current_phase.until.get("action") == "next_step"
    assert not coach.maybe_advance(session, 1, "next_step")
    assert coach.maybe_advance(session, 0, "next_step")


def test_coach_gates_navigation_while_collecting_entities():
    coach = TutorialCoach.load()
    session = Session()
    coach.maybe_advance(session, 0, None)  # welcome
    assert coach.gate_progress(session, 0) is True
    session.add_entity("apple-inc")
    coach.maybe_advance(session, 0, None)
    assert coach.gate_progress(session, 0) is True


def test_cli_tutorial_alias(monkeypatch):
    called = {}

    def fake_run_tutorial(client, *, session_path=None, output_path=None):
        called["session_path"] = session_path
        called["output_path"] = output_path

    monkeypatch.setattr("jstdata.workflows.run_tutorial", fake_run_tutorial)
    runner = CliRunner()
    result = runner.invoke(cli, ["tutorial", "--output", "out.json"])
    assert result.exit_code == 0, result.output
    assert called["output_path"] == "out.json"


def test_cli_workflows_run_tutorial(monkeypatch):
    called = {}

    def fake_run_tutorial(client, *, session_path=None, output_path=None):
        called["ran"] = True

    monkeypatch.setattr("jstdata.workflows.run_tutorial", fake_run_tutorial)
    runner = CliRunner()
    result = runner.invoke(cli, ["workflow", "run", "tutorial"])
    assert result.exit_code == 0, result.output
    assert called.get("ran") is True


def test_is_bundled_workflow():
    assert is_bundled_workflow("tutorial")
    assert not is_bundled_workflow("gdp-rank")
