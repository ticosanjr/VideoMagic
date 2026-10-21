"""Background music asset store and FFmpeg mix filter."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from videoflow.domain.errors import FilesystemError
from videoflow.runtime import portable_home

MAX_MUSIC_BYTES = 100 * 1024 * 1024
_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def music_dir() -> Path:
    directory = portable_home() / "assets" / "music"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_music() -> list[dict[str, object]]:
    return [
        {"file": str(path), "name": path.name, "size_bytes": path.stat().st_size}
        for path in sorted(music_dir().iterdir())
        if path.is_file() and path.suffix.casefold() in _SUFFIXES
    ]


def save_music(filename: str, data: bytes) -> dict[str, object]:
    if not data:
        raise FilesystemError("The music file is empty.")
    if len(data) > MAX_MUSIC_BYTES:
        raise FilesystemError("Music files must be at most 100 MB.")
    suffix = Path(filename).suffix.casefold()
    if suffix not in _SUFFIXES:
        raise FilesystemError("Use .mp3, .wav, .m4a, .aac, or .ogg.")
    digest = hashlib.sha256(data).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-") or "music"
    target = music_dir() / f"{stem}-{digest[:10]}{suffix}"
    target.write_bytes(data)
    return {
        "file": str(target),
        "name": target.name,
        "size_bytes": len(data),
        "sha256": digest,
    }


def music_filter(
    duration_sec: float,
    *,
    volume: float = 0.18,
    ducking: bool = True,
    fade_in_ms: int = 250,
    fade_out_ms: int = 500,
) -> str:
    duration = max(0.01, duration_sec)
    music = f"[1:a]volume={max(0.0, min(1.0, volume))},atrim=0:{duration:.3f}"
    fade_in = max(0, fade_in_ms) / 1000
    fade_out = max(0, fade_out_ms) / 1000
    if fade_in:
        music += f",afade=t=in:st=0:d={min(fade_in, duration):.3f}"
    if fade_out:
        start = max(0.0, duration - min(fade_out, duration))
        music += f",afade=t=out:st={start:.3f}:d={min(fade_out, duration):.3f}"
    music += "[music]"
    if ducking:
        return (
            music
            + ";[0:a]asplit=2[voice][side];"
            "[music][side]sidechaincompress="
            "threshold=0.03:ratio=8:attack=20:release=300[ducked];"
            "[voice][ducked]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
    return (
        music
        + ";[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
    )
