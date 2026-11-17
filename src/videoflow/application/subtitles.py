"""Shared subtitle sidecar resolution for video and delivery exports."""

from __future__ import annotations

from pathlib import Path


def resolve_subtitle_track(output: Path | str) -> Path | None:
    """Return the merged ASS track, preferring captions over title-only cards."""

    root = Path(output).expanduser()
    for name in ("subtitles.ass", "titles.ass"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


__all__ = ["resolve_subtitle_track"]
