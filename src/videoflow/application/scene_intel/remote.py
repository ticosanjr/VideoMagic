"""Remote Module A through the VideoFlow compute router."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from videoflow.application.scene_intel.detect import decupage_boundaries
from videoflow.application.scene_intel.io import write_json
from videoflow.application.scene_intel.manifest import save_manifest
from videoflow.application.scene_intel.pipeline import SceneAnalysisResult
from videoflow.application.scene_intel.proxy import SceneWorkspace, cache_key
from videoflow.application.scene_intel.supercontext import build_supercontext
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.state import MediaInfo

MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


def _safe_extract(archive: Path, destination: Path) -> None:
    """Extract a worker keyframe zip without allowing path traversal."""

    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise VideoFlowError("remote scene keyframe archive is too large")
        total = sum(member.file_size for member in members)
        if total > MAX_ARCHIVE_BYTES:
            raise VideoFlowError("remote scene keyframe archive exceeds the size limit")
        targets: list[tuple[Any, Path]] = []
        for member in members:
            if member.is_dir():
                continue
            parts = Path(member.filename).parts
            if parts and parts[0] == "keyframes":
                parts = parts[1:]
            if not parts:
                continue
            target = (destination.joinpath(*parts)).resolve()
            if destination not in target.parents:
                raise VideoFlowError("remote scene keyframe archive has an unsafe path")
            targets.append((member, target))
        for member, target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as reader, target.open("wb") as writer:
                writer.write(reader.read())


def _artifact_paths(result: dict[str, Any]) -> list[Path]:
    raw = result.get("paths")
    if isinstance(raw, list) and raw:
        return [Path(str(item)) for item in raw]
    path = result.get("path")
    return [Path(str(path))] if path else []


def _read_manifest(paths: list[Path]) -> tuple[dict[str, Any], Path | None]:
    for path in paths:
        if path.suffix.casefold() != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("scenes"), list):
            return payload, path
    raise VideoFlowError("remote scene analysis returned no manifest")


def analyze_scene_remote(
    router: Any,
    source: Path,
    workspace: SceneWorkspace,
    media: MediaInfo,
    *,
    threshold: float,
    min_scene_len_sec: float,
    source_topology: str,
    keyframe_size: int,
    video_id: str,
    decupage_plan: dict[str, Any] | None = None,
    asus: list[dict[str, Any]] | None = None,
    timeout_sec: float = 1800.0,
) -> SceneAnalysisResult:
    """Run Module A on the worker and materialize artifacts locally."""

    key = cache_key(
        video_sha=video_id,
        threshold=threshold,
        min_scene_len_sec=min_scene_len_sec,
        topology=source_topology,
        keyframe_size=keyframe_size,
    )
    duration = media.duration_frames * media.fps_den / max(1, media.fps_num)
    fps = media.fps_num / max(1, media.fps_den)
    boundaries, jumps = decupage_boundaries(
        decupage_plan,
        duration=duration,
        sample_rate=media.audio_sample_rate,
    )
    result = router.submit(
        "scene_analyze",
        {
            "inputs": [str(source)],
            "params": {
                "video_id": video_id,
                "width": media.width,
                "height": media.height,
                "fps": fps,
                "fps_num": media.fps_num,
                "fps_den": media.fps_den,
                "sample_rate": media.audio_sample_rate,
                "duration_sec": duration,
                "threshold": threshold,
                "min_scene_len_sec": min_scene_len_sec,
                "source_topology": source_topology,
                "keyframe_size": keyframe_size,
                "decupage_boundaries": sorted(boundaries),
                "decupage_jumps": sorted(jumps),
            },
            "timeout_sec": timeout_sec,
        },
        timeout=timeout_sec,
    )
    paths = _artifact_paths(result)
    payload, _ = _read_manifest(paths)
    archive = next(
        (path for path in paths if path.suffix.casefold() == ".zip"), None
    )
    if archive is not None:
        shutil.rmtree(workspace.keyframes, ignore_errors=True)
        workspace.keyframes.mkdir(parents=True, exist_ok=True)
        _safe_extract(archive, workspace.keyframes)
    warnings: list[str] = []
    for scene in payload.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        relative = str(scene.get("keyframe_path") or "")
        if not relative:
            continue
        candidate = workspace.keyframes / Path(relative).name
        if candidate.is_file():
            scene["keyframe_path"] = str(candidate)
        else:
            scene["keyframe_path"] = ""
            warnings.append(f"Remote keyframe missing for {scene.get('scene_id', '?')}")
    manifest = ScenesManifest.model_validate(payload)
    supercontext = build_supercontext(
        manifest,
        asus=asus,
        decupage_plan=decupage_plan,
        sample_rate=media.audio_sample_rate,
    )
    elapsed = float(result.get("elapsed_sec") or 0.0)
    save_manifest(
        workspace,
        manifest,
        key=key,
        engine="remote_scene_analyze",
        warnings=warnings,
        elapsed_sec=elapsed,
    )
    write_json(workspace.supercontext, supercontext)
    return SceneAnalysisResult(
        manifest=manifest,
        workspace=workspace,
        supercontext=supercontext,
        video_id=video_id,
        cache_key=key,
        engine="remote_scene_analyze",
        cache_hit=False,
        elapsed_sec=elapsed,
        warnings=warnings,
        keyframes_written=sum(
            1 for scene in manifest.scenes if scene.keyframe_path
        ),
        timings={"remote_total": round(elapsed, 4)},
    )


__all__ = ["analyze_scene_remote"]
