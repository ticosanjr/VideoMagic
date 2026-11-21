"""Structured execution telemetry shared by the router and MCP servers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(slots=True)
class ExecutionRecord:
    """One routed execution. Never serialize an empty ``{}`` for a job."""

    run_id: str
    capability: str
    execution_node: str
    device: str = ""
    model: str = ""
    vram_peak_mb: int = 0
    frames: int = 0
    in_duration_sec: float = 0.0
    out_duration_sec: float = 0.0
    rtf: float | None = None
    cache_hit: bool = False
    degraded: bool = False
    degraded_reason: str = ""
    started_at: str = ""
    finished_at: str = ""
    elapsed_sec: float = 0.0
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rtf"] = round(self.rtf, 6) if self.rtf is not None else None
        payload["elapsed_sec"] = round(self.elapsed_sec, 6)
        return payload


__all__ = ["ExecutionRecord", "now_iso"]
