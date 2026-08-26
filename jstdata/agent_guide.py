"""Generate the markdown agent bootstrap guide (`jst agent-guide`).

CLI commands and interactive steps are derived from the live Click tree and
step registry. Conceptual glue (data model, composition, resolution, host
chrome) is static prose that changes rarely.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from typing import Iterable

import click

from .workflows import list_steps

_PACKAGE = "jstdata"

_DATA_MODEL = """\
## Data model

- **Metric** — a measurable theme (e.g. GDP, employed-persons). Identified by a slug id.
- **Entity** — a context the metric is measured in (e.g. a country, a company). Slug id.
- **Taxonomy** — a membership catalog that defines a population of entities
  (e.g. `country`, `us-county`, `sec-central-index-key`). The main knob for scoping analysis.
- **Series** — one concrete time series: a metric observed for an entity (at a frequency).
- **Session** — staged analytical intent for interactive work: lists of metric / entity /
  series ids plus query filters (`taxonomy`, `head`/`tail`, `as_of`, `sort_by`, …).
  No observations are stored in the session; it is portable intent that can drive
  `query`, export, or a TUI pipeline.

Ids are opaque slugs. Display names are not ids.
"""

_COMPOSITION = """\
## Composition

Interactive investigation is composed in the shell, not a custom DSL:

```bash
jst run STEP [ARGS...] : STEP [ARGS...] : ...
```

- **Steps** are TUI screens that edit one shared session for the lifetime of the run.
- **Step args** (flags declared on each step) seed that step; they are not the session.
- **Saved workflows** (`jst workflows create` / `run`) persist step topology + step args
  only. Session state is interactive (or optionally preloaded with `--session`).
- Pipeline tokens for `workflows create` must follow a `--` boundary, e.g.
  `jst workflows create --id gdp-rank -- console : rank --taxonomy country`.
"""

_RESOLUTION = """\
## Resolution rule

Never invent metric, entity, taxonomy, or series ids from English names.

Always resolve via search or list commands (`jst metric search`, `jst entity search`,
`jst taxonomy ls`, …) before writing ids into a workflow, `--session` JSON, or
`jst query` flags. Prefer taxonomy-scoped search when the user names a population.
"""

_HOST_CHROME = """\
## Host chrome

Every `jst run` / `jst workflows run` process shares these keys (in addition to
step-specific bindings shown under `?`):

| Key | Action |
|-----|--------|
| `s` | Session modal — list / remove / inspect staged resources |
| `f` | Find modal — search metrics or entities and add to session |
| `e` | Export modal — copy Python/CLI or write session JSON |
| `n` / `p` | Next / previous step in the pipeline |
| `q` | Quit |
| `?` | Step-specific keybindings |
"""


def package_version() -> str:
    try:
        return version(_PACKAGE)
    except PackageNotFoundError:
        return "unknown"


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    line = text.strip().splitlines()[0].strip()
    # Click often embeds ``\\b`` blocks; collapse leftover whitespace.
    return re.sub(r"\s+", " ", line)


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _param_token(param: click.Parameter) -> str | None:
    """Compact signature fragment for one Click parameter."""
    if getattr(param, "hidden", False):
        return None
    if isinstance(param, click.Argument):
        name = (param.metavar or param.name or "ARG").upper()
        if param.nargs == -1:
            name = f"{name}..."
        return name if param.required else f"[{name}]"
    if isinstance(param, click.Option):
        # Prefer the long form.
        opt = next((o for o in param.opts if o.startswith("--")), None)
        if opt is None:
            opt = param.opts[0] if param.opts else f"--{param.name}"
        if param.is_flag or param.count:
            return opt if param.required else f"[{opt}]"
        meta = (param.metavar or param.name or "VALUE").upper()
        token = f"{opt} {meta}"
        return token if param.required else f"[{token}]"
    return None


def format_command_params(cmd: click.Command) -> str:
    parts: list[str] = []
    for param in cmd.params:
        token = _param_token(param)
        if token:
            parts.append(token)
    return " ".join(parts)


def iter_leaf_commands(
    root: click.Group,
    *,
    prog: str = "jst",
) -> Iterable[tuple[str, click.Command]]:
    """Yield ``(invocation, command)`` for every leaf command under ``root``."""

    def walk(cmd: click.Command, parts: list[str], ctx: click.Context) -> Iterable[tuple[str, click.Command]]:
        if isinstance(cmd, click.Group):
            for name in sorted(cmd.list_commands(ctx)):
                sub = cmd.get_command(ctx, name)
                if sub is None:
                    continue
                sub_ctx = click.Context(sub, info_name=name, parent=ctx)
                yield from walk(sub, parts + [name], sub_ctx)
            return
        invocation = " ".join(parts)
        yield invocation, cmd

    root_ctx = click.Context(root, info_name=prog)
    yield from walk(root, [prog], root_ctx)


def render_commands_table(root: click.Group) -> str:
    lines = [
        "| Command | Description | Parameters |",
        "|---------|-------------|------------|",
    ]
    for invocation, cmd in iter_leaf_commands(root):
        desc = _first_line(cmd.help) or _first_line(cmd.short_help) or ""
        params = format_command_params(cmd)
        lines.append(
            f"| `{_md_cell(invocation)}` | {_md_cell(desc)} | {_md_cell(params)} |"
        )
    return "\n".join(lines)


def _format_step_args(spec) -> str:
    if not spec.arguments:
        return "_(none)_"
    bits: list[str] = []
    for arg in spec.arguments:
        flag = arg.flag()
        piece = f"`{flag}`"
        if arg.required:
            piece += " (required)"
        elif arg.default is not None:
            piece += f" [default: `{arg.default}`]"
        if arg.choices:
            choices = ", ".join(f"`{c}`" for c in arg.choices)
            piece += f" {{{choices}}}"
        bits.append(piece)
    return ", ".join(bits)


def render_steps_section() -> str:
    specs = list_steps()
    lines = [
        "## Interactive steps",
        "",
        "Atoms for `jst run` / saved workflows. Order-agnostic: any step accepts an empty or arbitrary session.",
        "",
        "| Id | Name | Description | Arguments | Example |",
        "|----|------|-------------|-----------|---------|",
    ]
    if not specs:
        lines.append("| _(none registered)_ | | | | |")
        return "\n".join(lines)

    for spec in specs:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_md_cell(spec.id)}`",
                    _md_cell(spec.name),
                    _md_cell(spec.description),
                    _md_cell(_format_step_args(spec)),
                    f"`{_md_cell(spec.example or f'jst run {spec.id}')}`",
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("### Step details")
    for spec in specs:
        lines.append("")
        lines.append(f"#### `{spec.id}` — {spec.name}")
        lines.append("")
        lines.append(spec.description.strip())
        lines.append("")
        if spec.arguments:
            lines.append("Arguments:")
            lines.append("")
            for arg in spec.arguments:
                req = "required" if arg.required else "optional"
                default = (
                    f", default `{arg.default}`" if arg.default is not None else ""
                )
                lines.append(
                    f"- `{arg.flag()}` ({arg.type}, {req}{default}): {arg.description}"
                )
                if arg.choices:
                    lines.append(
                        f"  - Choices: {', '.join(f'`{c}`' for c in arg.choices)}"
                    )
            lines.append("")
        visible = [b for b in spec.bindings if b.show_in_help]
        if visible:
            lines.append("Step keybindings:")
            lines.append("")
            lines.append("| Key | Description |")
            lines.append("|-----|-------------|")
            for b in visible:
                lines.append(f"| `{_md_cell(b.key)}` | {_md_cell(b.description)} |")
            lines.append("")
        example = spec.example or f"jst run {spec.id}"
        lines.append(f"Example: `{example}`")
    return "\n".join(lines)


def render_agent_guide(cli_group: click.Group) -> str:
    """Build the full markdown guide for the given Click root group."""
    ver = package_version()
    sections = [
        f"# jstdata agent guide (v{ver})",
        "",
        "Bootstrap knowledge for agents helping a user with this installed CLI. "
        "Prefer this document over guessing command shapes or resource ids.",
        "",
        _DATA_MODEL.rstrip(),
        "",
        _COMPOSITION.rstrip(),
        "",
        _RESOLUTION.rstrip(),
        "",
        _HOST_CHROME.rstrip(),
        "",
        "## CLI commands",
        "",
        "One row per leaf command, derived from the installed CLI.",
        "",
        render_commands_table(cli_group),
        "",
        render_steps_section(),
        "",
    ]
    return "\n".join(sections)
