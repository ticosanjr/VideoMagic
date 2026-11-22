"""Shared router, audio extensions and naming helpers for the studio tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..toolkit.errors import InvalidArgumentError, MissingCommandError
from ..toolkit.router import RouterBridge

ROUTER = RouterBridge()
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus"}


def _output_name(value: str, default: str) -> str:
    raw = value.strip() if value else default
    name = Path(raw).name
    if name in {"", ".", ".."}:
        raise InvalidArgumentError(f"invalid output name: {value!r}")
    return name


def _stem_name(value: str) -> str:
    raw = str(value).strip().lower()
    cleaned = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_" for character in raw
    )
    if not cleaned or cleaned in {".", ".."}:
        raise InvalidArgumentError(
            f"invalid stem name: {value!r}",
            details={"argument": "stems", "value": value},
        )
    return cleaned


def _audio_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix in AUDIO_EXTENSIONS else ".wav"


def _ffmpeg() -> str:
    configured = os.environ.get("VF_FFMPEG")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise MissingCommandError(
        "ffmpeg is required for this tool; install it or set VF_FFMPEG",
        details={"env": ["VF_FFMPEG"], "executable": "ffmpeg"},
    )
