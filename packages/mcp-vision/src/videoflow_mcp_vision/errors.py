"""Typed errors raised by the VideoFlow media MCP tools."""

from __future__ import annotations

from typing import Any


class MediaToolError(RuntimeError):
    """Base error carrying a stable, machine-readable code."""

    code = "media_tool_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "message": str(self),
            "details": self.details,
        }


class InvalidArgumentError(MediaToolError):
    """A tool argument is missing, malformed, or unsafe."""

    code = "invalid_argument"


class InputNotFoundError(MediaToolError):
    """A required input file does not exist."""

    code = "input_not_found"


class MissingCommandError(MediaToolError):
    """No local executable or command template is configured."""

    code = "missing_command"


class CommandFailedError(MediaToolError):
    """An external command ran but failed."""

    code = "command_failed"

    def __init__(
        self,
        message: str,
        *,
        argv: list[str] | None = None,
        returncode: int | None = None,
        stderr: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(details or {})
        payload.update(
            {"argv": list(argv or []), "returncode": returncode, "stderr": stderr[-4000:]}
        )
        super().__init__(message, details=payload)
        self.argv = list(argv or [])
        self.returncode = returncode
        self.stderr = stderr


class OutputNotProducedError(MediaToolError):
    """A command succeeded but the expected output file is missing."""

    code = "output_not_produced"


class RemoteUnavailableError(MediaToolError):
    """A remote capability was requested but the router is not usable."""

    code = "remote_unavailable"


class RemoteResultError(MediaToolError):
    """A remote capability returned a result this tool cannot store."""

    code = "remote_result_invalid"
