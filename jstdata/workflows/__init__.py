"""Interactive steps composed on the shell.

::

    jst steps
    jst step console
    jst run console
    jst run console : discover --mode union
"""

from .base import (
    PipelineError,
    ResolvedStep,
    StepArgument,
    StepBinding,
    StepSpec,
    default_session_path,
    format_step_help,
    get_step,
    list_steps,
    parse_step_kwargs,
    resolve_pipeline,
    run_pipeline,
    split_pipeline,
)
from . import console as _console  # noqa: F401  — registers console
from . import discover as _discover  # noqa: F401  — registers discover

__all__ = [
    "PipelineError",
    "ResolvedStep",
    "StepArgument",
    "StepBinding",
    "StepSpec",
    "default_session_path",
    "format_step_help",
    "get_step",
    "list_steps",
    "parse_step_kwargs",
    "resolve_pipeline",
    "run_pipeline",
    "split_pipeline",
]
