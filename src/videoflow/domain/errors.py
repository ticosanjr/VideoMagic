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


class PathNotFoundError(VideoFlowError):
    """A filesystem browser path does not exist."""

    code = "path_not_found"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path does not exist: {path}")


class PathNotDirectoryError(VideoFlowError):
    """A filesystem browser path exists but is not a directory."""

    code = "not_a_directory"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path is not a directory: {path}")


class DirectoryExistsError(VideoFlowError):
    """A new output directory collides with an existing entry."""

    code = "directory_exists"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"A file or directory already exists: {path}")


class InvalidDirectoryNameError(VideoFlowError):
    """A new directory name is not a single portable path segment."""

    code = "invalid_directory_name"


class PermissionDeniedError(VideoFlowError):
    """The local filesystem denied a browser or create operation."""

    code = "permission_denied"


class FilesystemError(VideoFlowError):
    """The filesystem browser could not complete an operation."""

    code = "filesystem_error"


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


class TranscriptError(VideoFlowError):
    """A subtitle file cannot be parsed as a transcript."""

    code = "invalid_transcript"


class UnknownModuleError(VideoFlowError):
    """Unknown rack module id."""

    code = "unknown_module"

    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(f"Unknown module: {module}")


class ProjectNotFoundError(VideoFlowError):
    """Unknown project id."""

    code = "project_not_found"

    def __init__(self, project_id: object) -> None:
        self.project_id = str(project_id)
        super().__init__(f"Unknown project: {self.project_id}")


class ProjectStateError(VideoFlowError):
    """A project state or registry file is unreadable or inconsistent."""

    code = "project_state_invalid"


class ProjectExistsError(VideoFlowError):
    """A project root already belongs to another project."""

    code = "project_exists"


class MediaNotFoundError(VideoFlowError):
    """A media path does not point to a readable file."""

    code = "media_not_found"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Media file does not exist: {path}")


class MediaNotRegisteredError(VideoFlowError):
    """A project has no registered source media."""

    code = "media_not_registered"


class StateNotReadyError(VideoFlowError):
    """A project has no timeline to export yet."""

    code = "state_not_ready"


class ShortEditError(VideoFlowError):
    """A Short edit request cannot be applied to the completed run."""

    code = "short_edit_failed"


class TranscriptNotFoundError(VideoFlowError):
    """A project has no transcript yet."""

    code = "transcript_not_found"


class TranscriptRequiredError(VideoFlowError):
    """An enabled module needs a transcript that is not present."""

    code = "transcript_required"


class InvalidOverrideError(VideoFlowError):
    """A manual override refers to a sentence or word that does not exist."""

    code = "invalid_override"


class WordOverridesNotSupportedError(VideoFlowError):
    """The current culling engine operates on whole sentences only."""

    code = "word_overrides_not_supported"


class PresetNotFoundError(VideoFlowError):
    """Unknown shipped or operator preset."""

    code = "preset_not_found"

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Unknown preset: {name}")


class PresetError(VideoFlowError):
    """A preset file is unreadable or invalid."""

    code = "preset_invalid"


class InvalidPresetNameError(VideoFlowError):
    """A preset name would leave the operator preset directory."""

    code = "invalid_preset_name"


class CapabilityUnavailableError(VideoFlowError):
    """A route is part of the product contract but has no engine in this build."""

    code = "not_implemented"

    def __init__(self, capability: str, message: str) -> None:
        self.capability = capability
        super().__init__(message)

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["capability"] = self.capability
        return payload


class LlmError(VideoFlowError):
    """The OpenAI-compatible endpoint failed or returned unusable JSON."""

    code = "llm_failed"


class TranscriptionError(VideoFlowError):
    """Speech-to-text failed or returned unusable timestamps."""

    code = "transcription_failed"
