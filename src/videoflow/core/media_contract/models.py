"""Media contract errors and report models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from videoflow.core.media_contract.constants import MediaKind


class MediaContractError(RuntimeError):
    """A media file violates the canonical contract."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str = "",
        report: MediaReport | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.report = report

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error_code": self.code,
            "message": self.message,
        }
        if self.path:
            payload["path"] = self.path
        if self.report is not None:
            payload["report"] = self.report.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ExpectedMedia:
    duration_sec: float | None = None
    frames: int | None = None
    fps_num: int | None = None
    fps_den: int | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(slots=True)
class MediaReport:
    ok: bool
    kind: MediaKind
    path: str
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "path": self.path,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics),
        }
