"""Shared lifecycle state for background render workers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from videoflow.application.clock import now_iso


@dataclass
class WorkerState:
    """Progress, cancellation, and error fields common to render workers."""

    job_id: str
    status: str = "queued"
    percent: int = 0
    message: str = "Queued"
    error: str = ""
    error_details: dict[str, object] = field(default_factory=dict)
    started_at: str = field(default_factory=now_iso)
    finished_at: str = ""
    cancel_requested: bool = False
    cancel_event: Any = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "percent": self.percent,
            "message": self.message,
            "error": self.error,
            "error_details": dict(self.error_details),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
        }
