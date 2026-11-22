"""Shared handler protocol and error type."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

Handler = Callable[[dict[str, Any], list[Path], Path], Sequence[str | Path]]


class HandlerError(RuntimeError):
    """Raised by a handler when a job cannot produce its outputs."""
