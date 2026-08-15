"""Tests for the step catalog and jst run pipeline parser."""

from pathlib import Path

import pytest

from jstdata.session import Session
from jstdata.workflows.base import (
    PipelineError,
    StepArgument,
    StepSpec,
    apply_loaded_session,
    default_session_path,
    format_step_help,
    get_step,
    list_steps,
    load_session_or_empty,
    parse_step_kwargs,
    resolve_pipeline,
    split_pipeline,
)


def test_console_is_registered():
    import jstdata.workflows  # noqa: F401

    ids = [s.id for s in list_steps()]
    assert "console" in ids
    console = get_step("console")
    assert console.name == "Console"
    assert console.to_dict()["example"] == "jst run console"
    assert any(b["key"] == "i" for b in console.to_dict()["bindings"])


def test_format_step_help_console():
    text = format_step_help(get_step("console"))
    assert "Console" in text
    assert "jst run console" in text
    assert "Keybindings:" in text
    assert "inspect" in text.lower()


def test_default_session_path_is_well_formed():
    a = default_session_path("console")
    assert a.startswith("console-")
    assert a.endswith(".json")


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


def test_unknown_step_raises():
    with pytest.raises(KeyError, match="Unknown step"):
        get_step("nope")


def test_split_pipeline():
    assert split_pipeline(["console"]) == [["console"]]
    assert split_pipeline(["console", ":", "console"]) == [["console"], ["console"]]
    assert split_pipeline(
        ["company-selector", "--industry", "semiconductors", ":", "console"]
    ) == [["company-selector", "--industry", "semiconductors"], ["console"]]


def test_split_pipeline_errors():
    with pytest.raises(PipelineError, match="No steps"):
        split_pipeline([])
    with pytest.raises(PipelineError, match="Empty step"):
        split_pipeline([":", "console"])
    with pytest.raises(PipelineError, match="Trailing"):
        split_pipeline(["console", ":"])


def test_resolve_pipeline_console():
    resolved = resolve_pipeline(["console", ":", "console"])
    assert len(resolved) == 2
    assert resolved[0].spec.id == "console"
    assert resolved[0].kwargs == {}
    assert resolved[1].spec.id == "console"


def test_resolve_pipeline_unknown_step():
    with pytest.raises(KeyError, match="Unknown step"):
        resolve_pipeline(["not-a-step"])


def test_parse_step_kwargs():
    spec = StepSpec(
        id="demo",
        name="Demo",
        description="d",
        create_screen=lambda *a, **k: None,
        arguments=(
            StepArgument(
                name="industry",
                type="string",
                description="Industry filter",
            ),
            StepArgument(
                name="limit",
                type="integer",
                description="Max results",
                default=10,
            ),
        ),
    )
    assert parse_step_kwargs(spec, ["--industry", "semiconductors"]) == {
        "industry": "semiconductors",
        "limit": 10,
    }
    assert parse_step_kwargs(spec, ["--industry=chips", "--limit", "3"]) == {
        "industry": "chips",
        "limit": 3,
    }
    with pytest.raises(PipelineError, match="Unknown option"):
        parse_step_kwargs(spec, ["--nope"])
    with pytest.raises(PipelineError, match="integer"):
        parse_step_kwargs(spec, ["--limit", "x"])


def test_console_rejects_unknown_flags():
    with pytest.raises(PipelineError, match="Unknown option"):
        resolve_pipeline(["console", "--industry", "x"])
