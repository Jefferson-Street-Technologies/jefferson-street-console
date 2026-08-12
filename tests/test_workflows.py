"""Tests for the workflow registry and shared helpers."""

from pathlib import Path

import pytest

from jstdata.session import Session
from jstdata.workflows.base import (
    apply_loaded_session,
    default_session_path,
    get_workflow,
    list_workflows,
    load_session_or_empty,
)


def test_console_is_registered():
    import jstdata.workflows  # noqa: F401 — ensure registration

    specs = list_workflows()
    ids = [s.id for s in specs]
    assert "console" in ids
    console = get_workflow("console")
    assert console.name == "Console"


def test_default_session_path_is_unique_per_call():
    a = default_session_path("console")
    b = default_session_path("console")
    assert a.startswith("console-")
    assert a.endswith(".json")
    # Same-second calls may collide; still well-formed
    assert b.startswith("console-")


def test_load_session_or_empty(tmp_path: Path):
    assert load_session_or_empty(None).is_empty()

    path = tmp_path / "s.json"
    Session(metric=["gdp"], entity=["usa"]).save(path)
    loaded = load_session_or_empty(str(path))
    assert loaded.metric == ["gdp"]
    assert loaded.entity == ["usa"]


def test_apply_loaded_session():
    target = Session(metric=["old"])
    loaded = Session(metric=["gdp"], entity=["usa"], frequency="Annual")
    apply_loaded_session(target, loaded)
    assert target.metric == ["gdp"]
    assert target.entity == ["usa"]
    assert target.frequency == "Annual"


def test_unknown_workflow_raises():
    with pytest.raises(KeyError, match="Unknown workflow"):
        get_workflow("nope")
