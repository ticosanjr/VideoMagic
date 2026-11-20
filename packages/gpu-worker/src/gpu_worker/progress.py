"""Cooperative progress reporting for worker handlers.

Handlers are plain callables, so progress is passed through a context variable
instead of changing every signature. The job runner binds a reporter before it
invokes the handler; stages reported here are persisted in SQLite and exposed by
``/jobs/{id}``, ``/api/jobs`` and ``/api/overview``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ProgressReporter = Callable[[str, int], None]

_reporter: ContextVar[ProgressReporter | None] = ContextVar(
    "vf_gpu_progress", default=None
)


def clamp_progress(value: int | float) -> int:
    """Clamp a percentage to ``0..100``."""

    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def report(stage: str, progress: int | float) -> None:
    """Report the current stage and percentage to the bound job runner."""

    reporter = _reporter.get()
    if reporter is None:
        return
    clean_stage = str(stage or "").strip()[:80] or "running"
    reporter(clean_stage, clamp_progress(progress))


@contextmanager
def bind(reporter: ProgressReporter) -> Iterator[None]:
    """Bind ``reporter`` for every handler call inside the context."""

    token = _reporter.set(reporter)
    try:
        yield
    finally:
        _reporter.reset(token)


__all__ = ["ProgressReporter", "bind", "clamp_progress", "report"]
