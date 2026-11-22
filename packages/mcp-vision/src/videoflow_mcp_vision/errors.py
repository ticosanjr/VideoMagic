"""Compatibility shim for the vision typed errors."""

from __future__ import annotations

from videoflow.domains.vision.errors import (
    CommandFailedError,
    InputNotFoundError,
    InvalidArgumentError,
    MediaToolError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
    RemoteUnavailableError,
)

__all__ = [
    "CommandFailedError",
    "InputNotFoundError",
    "InvalidArgumentError",
    "MediaToolError",
    "MissingCommandError",
    "OutputNotProducedError",
    "RemoteResultError",
    "RemoteUnavailableError",
]
