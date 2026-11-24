"""Attach an existing local or curated music track to a project."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..toolkit import storage
from ..toolkit.assets import _ensure_input, _payload
from ..toolkit.errors import InvalidArgumentError
from .studio_common import _output_name


def attach_music_track(
    project_id: str,
    music_path: str,
    *,
    output_name: str = "music.wav",
) -> dict[str, Any]:
    """Attach an existing local or curated track without generating audio."""

    tool = "attach_music_track"
    source = _ensure_input(music_path, "music_path")
    name = _output_name(output_name or source.name, "music.wav")
    if not Path(name).suffix:
        name = f"{name}.wav"
    relative = f"assets/audio/{name}"
    key = storage.cache_key(tool, storage.file_fingerprint(source))
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise InvalidArgumentError(
            "music_path could not be copied into the project",
            details={"argument": "music_path", "path": str(source), "error": str(exc)},
        ) from exc
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="music",
        license="unknown",
        source="local:attach",
        cache_key=key,
        metadata={
            "music_path": str(source),
            "original_name": source.name,
            "duration_sec": 0.0,
        },
    )
    return _payload(tool, project_id, record, mode="local", music_path=str(source))


__all__ = ["attach_music_track"]
