"""Tests for ``jst agent-guide``."""

from click.testing import CliRunner

from jstdata.agent_guide import (
    format_command_params,
    iter_leaf_commands,
    package_version,
    render_agent_guide,
)
from jstdata.cli import cli
from jstdata.workflows import list_steps


def test_agent_guide_cli():
    runner = CliRunner()
    result = runner.invoke(cli, ["agent-guide"])
    assert result.exit_code == 0
    out = result.output
    assert out.startswith("# jstdata agent guide (v")
    assert "## Data model" in out
    assert "## Composition" in out
    assert "## Resolution rule" in out
    assert "## Host chrome" in out
    assert "## CLI commands" in out
    assert "## Interactive steps" in out
    assert "`jst agent-guide`" in out
    assert "`jst metric search`" in out
    assert "`jst workflows create`" in out
    assert "`jst run`" in out
    assert "Never invent" in out


def test_agent_guide_lists_all_leaf_commands():
    guide = render_agent_guide(cli)
    for invocation, _cmd in iter_leaf_commands(cli):
        assert f"`{invocation}`" in guide, invocation


def test_agent_guide_lists_all_steps():
    guide = render_agent_guide(cli)
    specs = list_steps()
    assert specs, "expected registered steps"
    for spec in specs:
        assert f"`{spec.id}`" in guide
        if spec.example:
            assert spec.example in guide


def test_format_command_params_includes_options():
    # Pick a known leaf with several options.
    cmd = None
    for invocation, leaf in iter_leaf_commands(cli):
        if invocation == "jst metric search":
            cmd = leaf
            break
    assert cmd is not None
    params = format_command_params(cmd)
    assert "QUERY" in params or "[QUERY]" in params
    assert "--taxonomy" in params
    assert "--format" in params


def test_package_version_nonempty():
    assert package_version()
    assert package_version() != ""
