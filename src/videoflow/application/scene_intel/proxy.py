"""Analysis proxy and content-addressed workspace layout."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.core.media_contract import PIPELINE_SCHEMA_VERSION
from videoflow.domain.state import MediaInfo

PROXY_HEIGHT = 360
KEYFRAME_SIZE = 544
KEYFRAME_QUALITY = 78
CACHE_VERSION = "4.0"


def file_sha256(path: Path, *, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_video_id(value: str) -> str:
    candidate = str(value or "").strip()
    if (
        not candidate
        or not _SAFE_ID.match(candidate)
        or candidate in {".", ".."}
        or ".." in candidate.split(".")
    ):
        raise ValueError(f"invalid scene cache id: {value!r}")
    return candidate


@dataclass(frozen=True, slots=True)
class SceneWorkspace:
    root: Path
    proxy: Path
    keyframes: Path
    manifest: Path
    supercontext: Path


def scene_workspace(workspace: Path, video_id: str) -> SceneWorkspace:
    root = Path(workspace).expanduser() / safe_video_id(video_id)
    return SceneWorkspace(
        root=root,
        proxy=root / "proxy_360.mp4",
        keyframes=root / "keyframes",
        manifest=root / "scenes_manifest.json",
        supercontext=root / "timeline_supercontext.json",
    )


def ensure_proxy(
    source: Path,
    media: MediaInfo,
    workspace: SceneWorkspace,
    *,
    force: bool = False,
) -> tuple[Path, bool]:
    """Return the 360p analysis proxy, building it when missing."""

    if media.height <= PROXY_HEIGHT:
        # A source already at or below the analysis height needs no re-encode.
        return Path(source).expanduser(), False
    if workspace.proxy.is_file() and workspace.proxy.stat().st_size > 0 and not force:
        return workspace.proxy, False
    workspace.root.mkdir(parents=True, exist_ok=True)
    FFmpegAdapter().build_proxy(
        source,
        workspace.proxy,
        height=PROXY_HEIGHT,
        preset="ultrafast",
        crf=30,
        audio=False,
        fps=3,
        fast=True,
    )
    return workspace.proxy, True


def cache_key(
    *,
    video_sha: str,
    threshold: float,
    min_scene_len_sec: float,
    topology: str,
    keyframe_size: int = KEYFRAME_SIZE,
) -> str:
    payload = "|".join(
        [
            f"v={CACHE_VERSION}",
            f"schema={PIPELINE_SCHEMA_VERSION}",
            video_sha,
            f"threshold={round(float(threshold), 4)}",
            f"min_len={round(float(min_scene_len_sec), 4)}",
            f"topology={topology}",
            f"keyframe={int(keyframe_size)}",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "CACHE_VERSION",
    "KEYFRAME_QUALITY",
    "KEYFRAME_SIZE",
    "PROXY_HEIGHT",
    "SceneWorkspace",
    "cache_key",
    "ensure_proxy",
    "file_sha256",
    "safe_video_id",
    "scene_workspace",
]
