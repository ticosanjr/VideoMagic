"""Result object and failure type for the canonical audio stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from videoflow.domain.errors import ExportError


class AudioFinalizeError(ExportError):
    """The canonical audio bed could not be produced as requested."""

    code = "audio_finalize_failed"


@dataclass(slots=True)
class AudioFinalizeResult:
    ok: bool
    path: str
    duration_sec: float
    sample_rate: int
    channels: int
    codec: str
    integrated_lufs: float
    true_peak_db: float
    mono_repaired: bool = False
    music_mixed: bool = False
    sfx_events_requested: int = 0
    sfx_events_mixed: int = 0
    warnings: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "duration_sec": round(self.duration_sec, 6),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "codec": self.codec,
            "integrated_lufs": round(self.integrated_lufs, 3),
            "true_peak_db": round(self.true_peak_db, 3),
            "mono_repaired": self.mono_repaired,
            "music_mixed": self.music_mixed,
            "sfx_events_requested": self.sfx_events_requested,
            "sfx_events_mixed": self.sfx_events_mixed,
            "warnings": list(self.warnings),
            "filters": list(self.filters),
        }


__all__ = ["AudioFinalizeError", "AudioFinalizeResult"]
