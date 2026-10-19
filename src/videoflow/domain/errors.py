"""Typed failures. Route handlers and MCP tools translate these; they do not invent new ones."""

from __future__ import annotations

from collections.abc import Sequence


class VideoFlowError(Exception):
    """Base class for expected VideoFlow failures."""

    code = "videoflow_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, object]:
        return {"ok": False, "code": self.code, "message": self.message}


class NotImplementedCapabilityError(VideoFlowError):
    """A specified tool or module has no engine in this build."""

    code = "not_implemented"

    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"{capability} is specified but not implemented in this scaffold.")

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["tool"] = self.capability
        return payload


class UpstreamDirtyError(VideoFlowError):
    """A single-module run was asked to ignore dirty ancestors."""

    code = "upstream_dirty"

    def __init__(self, target: str, ancestors: Sequence[str]) -> None:
        self.target = target
        self.ancestors = tuple(ancestors)
        names = ", ".join(self.ancestors) if self.ancestors else "(none)"
        super().__init__(f"Cannot run {target}: upstream modules are not cached: {names}")

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["target"] = self.target
        payload["ancestors"] = list(self.ancestors)
        return payload


class ModuleBypassedError(VideoFlowError):
    """The caller asked to execute a module that is switched off."""

    code = "module_bypassed"

    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(f"Module {module} is bypassed. Enable it before running it.")


class JobAlreadyRunningError(VideoFlowError):
    """One project may have only one active job."""

    code = "job_already_running"

    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(f"A job is already running ({module}). Cancel it before starting another.")


class PathJailError(VideoFlowError):
    """A path resolved outside the configured allowlist."""

    code = "path_not_allowed"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path is outside the allowlist: {path}")


class InvalidRetakeIdsError(VideoFlowError):
    """The model returned sentence ids that were not in the prompt window."""

    code = "invalid_retake_ids"

    def __init__(self, unknown_ids: Sequence[int]) -> None:
        self.unknown_ids = tuple(sorted(set(unknown_ids)))
        rendered = ", ".join(str(item) for item in self.unknown_ids)
        super().__init__(f"Retake response contains unknown sentence ids: {rendered}")

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["unknown_ids"] = list(self.unknown_ids)
        return payload


class InvalidTimeError(VideoFlowError):
    """A time value violates the rational timebase rules."""

    code = "invalid_time"


class IngestError(VideoFlowError):
    """FFmpeg or FFprobe could not read the source."""

    code = "ingest_failed"


class ExportError(VideoFlowError):
    """The timeline cannot be represented as a valid NLE document."""

    code = "export_failed"


class JobCancelledError(VideoFlowError):
    """The job stopped because the caller cancelled it."""

    code = "job_cancelled"


class JobQueueFullError(VideoFlowError):
    """The local job limit is reached."""

    code = "job_queue_full"


class JobNotFoundError(VideoFlowError):
    """Unknown job id."""

    code = "job_not_found"
