"""Background music asset store and FFmpeg mix filter."""

from __future__ import annotations

from pathlib import Path

from videoflow.domain.errors import AssetNotFoundError
from videoflow.domains.media.asset_store import list_files, save_file
from videoflow.runtime import portable_home

MAX_MUSIC_BYTES = 100 * 1024 * 1024
_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def music_dir() -> Path:
    directory = portable_home() / "assets" / "music"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_music() -> list[dict[str, object]]:
    return list_files(music_dir(), _SUFFIXES)


def save_music(filename: str, data: bytes) -> dict[str, object]:
    return save_file(
        filename,
        data,
        directory=music_dir(),
        suffixes=_SUFFIXES,
        max_bytes=MAX_MUSIC_BYTES,
        label="music",
        default_stem="music",
    )


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


def delete_music(name: str) -> None:
    target = music_dir() / Path(name).name
    if target.parent != music_dir() or not target.is_file():
        raise AssetNotFoundError(f"Unknown music asset: {name}")
    target.unlink()
