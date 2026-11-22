"""Font files that must accompany a remote ASS render."""

from __future__ import annotations

from videoflow.application.fonts import fonts_dir

FONT_SUFFIXES = {".ttf", ".otf"}


def remote_font_paths() -> list[str]:
    """Return the portable font files to upload for a remote render."""

    directory = fonts_dir()
    try:
        files = sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.casefold() in FONT_SUFFIXES
        )
    except OSError:
        return []
    return [str(path) for path in files[:64]]


__all__ = ["remote_font_paths"]
