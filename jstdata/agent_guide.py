"""Generate the markdown agent bootstrap guide (`jst agent-guide`).

CLI commands, interactive steps, and session field names are derived from the
live Click tree, step registry, and ``Session`` dataclass. Conceptual glue
(data model, composition, resolution, host chrome, session how-to) is static
prose that changes rarely.
"""

from __future__ import annotations

import re
from dataclasses import fields
from importlib.metadata import PackageNotFoundError, version
from typing import Iterable, get_args, get_origin

import click

from .session import Session
from .workflows import list_steps

_PACKAGE = "jstdata"

_DATA_MODEL = """\
## Data model

- **Metric** — a measurable theme (e.g. GDP, employed-persons). Identified by a slug id.
- **Entity** — a context the metric is measured in (e.g. a country, a company). Slug id.
- **Taxonomy** — a membership catalog that defines a population of entities
  (e.g. `country`, `us-county`, `sec-central-index-key`). The main knob for scoping analysis.
- **Series** — one concrete time series: a metric observed for an entity (at a frequency).
- **Session** — portable analytical intent (resource ids + query filters). See **Sessions**
  below. No observations live in a session file.

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
  only. Bake discovered metrics/entities into a **session JSON** and pass `--session`
  when running (see **Sessions**).
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

_SESSION_HOWTO = """\
### Create and modify

**Write a JSON file** (usual agent path after resolving ids):

```json
{
  "metric": ["employed-persons", "unemployment-rate"],
  "taxonomy": "country",
  "tail": 1,
  "sort_by": "value"
}
```

Omit unused fields. Empty lists may be omitted. Ids must already be resolved.

**Python API** (same shape as the JSON file):

```python
from jstdata import Session

session = Session(
    metric=["employed-persons", "unemployment-rate"],
    taxonomy="country",
    tail=1,
    sort_by="value",
)
session.add_metric("gdp")          # no-op if already present
session.add_entity("united-states")
session.remove_id("gdp")           # removes from metric/entity/series
session.save("labor.json")         # write JSON
session = Session.load("labor.json")
```

Edit the JSON by hand or re-save from Python; there is no separate session CLI.

### Use with steps and workflows

Preload into a pipeline or saved workflow:

```bash
jst run --session labor.json rank --taxonomy country
jst workflows run gdp-rank --session labor.json
```

`--session` copies the file into the live session at startup. The user can still
change it in the TUI (`s` / `f`). Export with `e` to write a new JSON snapshot.

Typical pattern after metric discovery:

1. Resolve metric (and taxonomy) ids via search.
2. Write a session JSON with those `metric` ids (and optional filters).
3. Create or reuse a workflow whose steps consume session metrics (e.g. `rank`).
4. Hand the user: `jst workflows run <id> --session <file>.json`.
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


def _annotation_label(annotation: object) -> str:
    """Human-readable type for a Session field annotation."""
    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        inner = _annotation_label(args[0]) if args else "any"
        return f"list[{inner}]"
    if origin is not None:
        # Optional[T] / Union[T, None]
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return f"{_annotation_label(args[0])} | null"
    if annotation is str:
        return "string"
    if annotation is int:
        return "integer"
    if isinstance(annotation, type):
        return annotation.__name__
    text = str(annotation)
    return text.replace("typing.", "").replace("None", "null")


_SESSION_FIELD_NOTES: dict[str, str] = {
    "metric": "Resolved metric slug ids staged for the investigation",
    "entity": "Resolved entity slug ids",
    "series": "Resolved series slug ids (when targeting series directly)",
    "frequency": "Optional frequency filter (Annual, Quarterly, Monthly, Daily, Intraday)",
    "taxonomy": "Population scope; entity membership catalog slug",
    "head": "Earliest N observations per series for `/query`",
    "tail": "Latest N observations per series for `/query`",
    "as_of": "Timezone-aware ISO-8601 cutoff on release_timestamp",
    "sort_by": "`id` (default) or `value` (desc) for `/query` ordering",
    "start_date": "Legacy/deep-history field; not sent to `/query`",
    "end_date": "Legacy/deep-history field; not sent to `/query`",
    "start_time": "Legacy/deep-history field; not sent to `/query`",
    "end_time": "Legacy/deep-history field; not sent to `/query`",
    "order_by": "Observation order preference where applicable (`asc`/`desc`)",
}


def render_session_section() -> str:
    """Sessions how-to plus a field table derived from ``Session``."""
    lines = [
        "## Sessions",
        "",
        "A **session** is the portable bag of resource ids and filters that steps share.",
        "It mirrors `jst query` / `JSTDataClient.query` intent: no observations, only what",
        "is needed to (re)run a query or drive a TUI pipeline.",
        "",
        "Saved workflows do **not** store session contents. After discovering metrics or",
        "entities, write them into a session JSON and pass `--session` on `jst run` or",
        "`jst workflows run`. Steps such as `rank` (metrics in session) and `discover`",
        "(entities in session) read that staged state.",
        "",
        "### Session JSON fields",
        "",
        "Derived from the installed `Session` model. Write a UTF-8 JSON object;",
        "`Session.save` / `Session.load` use this shape.",
        "",
        "| Field | Type | Notes |",
        "|-------|------|-------|",
    ]
    for f in fields(Session):
        note = _SESSION_FIELD_NOTES.get(f.name, "")
        lines.append(
            f"| `{_md_cell(f.name)}` | {_md_cell(_annotation_label(f.type))} | {_md_cell(note)} |"
        )
    lines.append("")
    lines.append(_SESSION_HOWTO.rstrip())
    return "\n".join(lines)


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
        render_session_section(),
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
