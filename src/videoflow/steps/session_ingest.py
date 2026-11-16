"""Multi-take session ingest: order, normalize, and build a multi-source timeline."""

from __future__ import annotations

import hashlib
import json
import wave
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import adapter_for, digest_payload
from videoflow.steps.registry import register_step


class SessionIngestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[str] = Field(default_factory=list)
    raw_dir: str = ""
    order: Literal["auto", "name", "mtime", "timecode"] = "auto"
    target_fps: float = Field(default=0.0, ge=0.0, le=240.0)
    target_width: int = Field(default=0, ge=0, le=7680)
    target_height: int = Field(default=0, ge=0, le=4320)
    normalize: bool = False
    keep_originals: bool = True
    extract_audio: bool = True


def _natural(name: str) -> tuple[object, ...]:
    parts: list[object] = []
    number = ""
    for char in name:
        if char.isdigit():
            number += char
            continue
        if number:
            parts.append(int(number))
            number = ""
        parts.append(char.casefold())
    if number:
        parts.append(int(number))
    return tuple(parts)


def _discover(options: SessionIngestParams) -> list[Path]:
    paths = [
        resolve_allowed(Path(item).expanduser(), allowed_roots())
        for item in options.sources
        if str(item).strip()
    ]
    if options.raw_dir.strip():
        directory = resolve_allowed(Path(options.raw_dir).expanduser(), allowed_roots())
        if not directory.is_dir():
            raise IngestError(f"Session directory does not exist: {directory}")
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in {
                ".mp4",
                ".mov",
                ".mkv",
                ".m4v",
                ".avi",
            }:
                paths.append(path)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    if not unique:
        raise IngestError("No session clips were found")
    return unique


def _sort(paths: list[Path], order: str) -> list[Path]:
    if order == "name":
        return sorted(paths, key=lambda path: _natural(path.name))
    if order == "mtime":
        return sorted(paths, key=lambda path: (path.stat().st_mtime_ns, _natural(path.name)))
    if order == "timecode":
        from videoflow.adapters.ffmpeg import FFmpegAdapter

        adapter = FFmpegAdapter()

        def key(path: Path) -> tuple[object, ...]:
            info = adapter.probe(path)
            return (
                info.start_timecode_frames,
                path.stat().st_mtime_ns,
                _natural(path.name),
            )

        return sorted(paths, key=key)
    return sorted(paths, key=lambda path: (path.stat().st_mtime_ns, _natural(path.name)))


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _concat_pcm(files: list[Path], target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as output:
        params = None
        for path in files:
            with wave.open(str(path), "rb") as source:
                if params is None:
                    params = source.getparams()
                    output.setparams(params)
                if source.getparams()[:3] != params[:3]:
                    raise IngestError("Session audio streams do not share a PCM format")
                output.writeframes(source.readframes(source.getnframes()))
    return target


@register_step
class SessionIngestStep(BaseStep):
    type = "session.ingest"
    title = "Session ingest"
    description = "Order, normalize, and build a multi-source timeline from a recording session."
    produces = ("session_manifest", "timeline")
    params_model = SessionIngestParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = SessionIngestParams.model_validate(params)
        adapter = adapter_for(context, io)
        paths = _sort(_discover(options), options.order)
        io.report(5, f"Ordering {len(paths)} session clip(s)")
        probes = [adapter.probe(path) for path in paths]
        primary = probes[0]
        target_width = options.target_width or primary.width
        target_height = options.target_height or primary.height
        target_rate = primary.audio_sample_rate
        if options.target_fps > 0:
            fraction = Fraction(str(options.target_fps)).limit_denominator(1001)
            fps_num, fps_den = fraction.numerator, fraction.denominator
        else:
            fps_num, fps_den = primary.fps_num, primary.fps_den
        session_dir = context.work / "session"
        session_dir.mkdir(parents=True, exist_ok=True)
        sources: dict[str, MediaInfo] = {}
        manifest_clips: list[dict[str, object]] = []
        pcm_files: list[Path] = []
        for index, (path, info) in enumerate(zip(paths, probes, strict=True), start=1):
            io.check_cancel()
            mismatch = (
                info.fps_num != fps_num
                or info.fps_den != fps_den
                or info.width != target_width
                or info.height != target_height
                or info.audio_sample_rate != target_rate
            )
            material = path
            if options.normalize or mismatch:
                io.report(10 + int(index / max(1, len(paths)) * 55), f"Normalizing clip {index}")
                material = adapter.normalize_session_source(
                    path,
                    session_dir / f"src{index:03d}.mp4",
                    width=target_width,
                    height=target_height,
                    fps_num=fps_num,
                    fps_den=fps_den,
                    sample_rate=target_rate,
                )
                info = adapter.probe(material)
            source_id = f"src{index:03d}"
            sources[source_id] = info
            if options.extract_audio:
                pcm = adapter.extract_pcm(
                    material,
                    session_dir / f"src{index:03d}.wav",
                    sample_rate=16000,
                )
                pcm_files.append(pcm)
            manifest_clips.append(
                {
                    "source_id": source_id,
                    "original": str(path),
                    "material": str(material),
                    "normalized": material != path,
                    "sha256": _sha256(material),
                    "fps_num": info.fps_num,
                    "fps_den": info.fps_den,
                    "width": info.width,
                    "height": info.height,
                    "duration_frames": info.duration_frames,
                    "audio_sample_rate": info.audio_sample_rate,
                }
            )

        timeline_frames = 0
        timeline_samples = 0
        video_segments: list[VideoSegment] = []
        audio_segments: list[AudioSegment] = []
        for index, (source_id, info) in enumerate(sources.items(), start=1):
            duration_samples = round(
                info.duration_frames / (info.fps_num / info.fps_den) * target_rate
            )
            clip_id = f"session-{index:03d}"
            video_segments.append(
                VideoSegment(
                    clip_id=clip_id,
                    source_id=source_id,
                    source_in_frame=0,
                    source_out_frame=info.duration_frames,
                    timeline_in_frame=timeline_frames,
                    timeline_out_frame=timeline_frames + info.duration_frames,
                )
            )
            audio_segments.append(
                AudioSegment(
                    clip_id=clip_id,
                    source_id=source_id,
                    source_in_sample=0,
                    source_out_sample=duration_samples,
                    timeline_in_sample=timeline_samples,
                    timeline_out_sample=timeline_samples + duration_samples,
                )
            )
            timeline_frames += info.duration_frames
            timeline_samples += duration_samples
        primary_media = primary.model_copy(
            update={
                "width": target_width,
                "height": target_height,
                "fps_num": fps_num,
                "fps_den": fps_den,
                "duration_frames": timeline_frames,
            }
        )
        state = ProjectState(
            media_info=primary_media,
            sources=sources,
            primary_source_id=next(iter(sources)),
            video_segments=video_segments,
            audio_segments=audio_segments,
            transcript=list(context.transcript),
        )
        context.state = state
        context.media = primary_media
        context.source = Path(sources[state.primary_source_id].source_path)
        session_audio = None
        if pcm_files:
            session_audio = _concat_pcm(pcm_files, session_dir / "session_audio.wav")
            context.pcm_path = session_audio
            context.pcm_digest = _sha256(session_audio)
        manifest = {
            "schema_version": 1,
            "clip_count": len(paths),
            "order": options.order,
            "target": {
                "width": target_width,
                "height": target_height,
                "fps_num": fps_num,
                "fps_den": fps_den,
                "audio_sample_rate": target_rate,
            },
            "total_frames": timeline_frames,
            "clips": manifest_clips,
            "session_audio": str(session_audio) if session_audio is not None else "",
            "sources": {
                source_id: info.model_dump(mode="json") for source_id, info in sources.items()
            },
        }
        target = session_dir / "session_manifest.json"
        target.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        context.metadata["session_manifest"] = manifest
        if session_audio is not None:
            context.metadata["session_audio"] = str(session_audio)
            context.artifacts["session_audio"] = str(session_audio)
        context.artifacts["session_manifest"] = str(target)
        context.hashes["session.ingest"] = digest_payload(manifest)
        io.report(100, f"Session ready: {len(paths)} clip(s), {timeline_frames} frames")
