"""One validated timeline to the full delivery set.

The bundle is the single entry point behind ``vf_export()`` and
the ``delivery.package`` targets. It never re-analyses the timeline: the same
``ProjectState`` feeds every NLE document and the social master.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.application.disk import (
    ensure_free_space_for_export,
    prune_render_segments,
)
from videoflow.application.export_service import (
    ALL_TARGETS,
    resolve_targets,
)
from videoflow.application.master_export import look_from_mapping, render_master
from videoflow.application.nle_extras import nle_extras_from_output
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.application.subtitles import resolve_subtitle_track
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.domain.timebase import Rounding
from videoflow.domains.media import license_blockers
from videoflow.exporters.common import timeline_duration_frames, timeline_duration_samples
from videoflow.exporters.extras import NleExtras
from videoflow.exporters.fcpxml import Dialect
from videoflow.exporters.mp4 import (
    YOUTUBE_AUDIO_BITRATE,
    YOUTUBE_LUFS,
    YOUTUBE_PROFILE,
    YOUTUBE_TRUE_PEAK_DB,
    ExportMode,
    video_encoder,
)


class TimelineRequiredError(ExportError):
    """The project has no validated timeline to deliver."""

    code = "timeline_required"


BUNDLE_SCHEMA_VERSION = 1
BUNDLE_FILENAME = "bundle.json"
BUNDLE_FILENAMES: dict[str, str] = {
    "mp4": "youtube_master.mp4",
    "resolve": "resolve_timeline.fcpxml",
    "premiere": "premiere_timeline.xml",
    "kdenlive": "kdenlive_project.kdenlive",
    "kdenlive_mlt": "kdenlive_project.mlt",
    "edl": "timeline.edl",
}
LEGACY_BUNDLE_FILENAMES: dict[str, str] = {
    "mp4": "final_youtube.mp4",
    "resolve": "timeline_resolve.fcpxml",
    "premiere": "timeline_premiere.xml",
    "kdenlive": "timeline_kdenlive.kdenlive",
    "kdenlive_mlt": "timeline_kdenlive.mlt",
}
DEFAULT_BUNDLE_TARGETS: tuple[str, ...] = ("mp4_youtube", "resolve", "premiere", "kdenlive")


@dataclass(frozen=True, slots=True)
class DeliveryBundleRequest:
    """Options for a multi-target delivery run."""

    targets: tuple[str, ...] = DEFAULT_BUNDLE_TARGETS
    dialect: Dialect = "1.10"
    mp4_profile: str = YOUTUBE_PROFILE
    mp4_audio_bitrate: str = YOUTUBE_AUDIO_BITRATE
    mp4_loudness_lufs: float | None = YOUTUBE_LUFS
    mp4_true_peak_db: float = YOUTUBE_TRUE_PEAK_DB
    mp4_cfr: bool = True
    mp4_crf: int = 18
    mp4_preset: str = "veryfast"
    mp4_draft: bool = False
    mp4_mode: ExportMode = "final"
    mp4_fps: int | str = 30
    audio_source: str = "mix"
    look: dict[str, Any] | None = None
    burn_subtitles: bool = True
    require_licenses: bool = True
    include_sidecars: bool = True
    extra_targets: tuple[str, ...] = field(default_factory=tuple)
    compute_policy: str = "auto"
    allow_slow_cpu_fallback: bool = True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def blocked_paths(blockers: Sequence[dict[str, Any]], base: Path) -> set[str]:
    paths: set[str] = set()
    for item in blockers:
        for key in ("path", "title", "local_path", "asset_path"):
            value = str(item.get(key) or "").strip()
            if not value:
                continue
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = Path(base) / candidate
            paths.add(str(candidate))
            paths.add(candidate.name)
    return paths


def _fps_value(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().casefold() in {"source", "auto", ""}:
            return None
        try:
            value = int(value)
        except ValueError:
            return None
    return value if int(value) > 0 else None


def timeline_frames(state: ProjectState) -> int:
    media = state.media_info
    if media is None:
        return 0
    samples = timeline_duration_samples(state)
    audio_frames = media.timebase().sample_to_frame(samples, Rounding.CEIL)
    return max(timeline_duration_frames(state), audio_frames)


def _copy_audio_24bit(source: Path, target: Path) -> bool:
    from videoflow.runtime import find_binary

    binary = find_binary("ffmpeg")
    if binary is None:
        return False
    import subprocess

    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-c:a",
            "pcm_s24le",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and target.is_file()


def _copy_sidecars(output: Path, destination: Path) -> list[str]:
    sidecars = destination / "sidecars"
    sidecars.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for relative in (
        "titles.ass",
        "titles.json",
        "captions/captions.ass",
        "captions/captions.srt",
        "subtitles.ass",
        "broll.json",
        "timeline_meta.json",
        "audio/master.wav",
        "audio/master-filters.json",
        "audio/ducking.json",
        "color/filters.json",
        "assets/licenses.json",
        "assets/licenses.md",
        "assets/assignments.json",
    ):
        source = output / relative
        if not source.is_file():
            continue
        target = sidecars / Path(relative).name
        if relative == "audio/master.wav" and _copy_audio_24bit(source, target):
            copied.append(target.name)
            continue
        shutil.copy2(source, target)
        copied.append(target.name)
    return copied


def _mp4_metadata(path: Path) -> dict[str, Any]:
    """Best-effort probe of the social master without failing the bundle."""

    if not path.is_file():
        return {"exists": False}
    try:
        from videoflow.adapters.ffmpeg import FFmpegAdapter

        media = FFmpegAdapter().probe(path)
    except Exception as exc:  # noqa: BLE001 - probe is advisory
        return {"exists": True, "size": path.stat().st_size, "probe_error": str(exc)}
    return {
        "exists": True,
        "size": path.stat().st_size,
        "duration_frames": media.duration_frames,
        "width": media.width,
        "height": media.height,
        "fps_num": media.fps_num,
        "fps_den": media.fps_den,
        "audio_sample_rate": media.audio_sample_rate,
    }


def build_delivery_bundle(
    state: ProjectState,
    output: Path,
    *,
    request: DeliveryBundleRequest | None = None,
    extras: NleExtras | None = None,
    adapter: Any | None = None,
    cache_dir: Path | None = None,
    progress: Callable[[str, int], None] | None = None,
    should_cancel: Callable[[], object] | None = None,
) -> dict[str, Any]:
    """Export every requested target and write ``exports/bundle.json``.

    Raises :class:`ExportError` when a required license is still blocked.
    """

    options = request or DeliveryBundleRequest()
    output = Path(output).expanduser()
    ensure_free_space_for_export(output, state)
    exports = output / "exports"
    exports.mkdir(parents=True, exist_ok=True)

    blockers = (
        license_blockers(output, state)
        if options.require_licenses
        else []
    )
    if blockers:
        titles = ", ".join(
            str(item.get("title") or item.get("asset_id") or "asset") for item in blockers[:6]
        )
        raise ExportError(
            "Asset licenses need review before delivery: "
            f"{titles}. Approve them at the assets review gate."
        )

    targets = resolve_targets([*options.targets, *options.extra_targets])
    if not targets:
        targets = list(ALL_TARGETS)
    nle_targets = [target for target in targets if target != "mp4"]
    format_for_target = {
        "resolve": "fcpxml",
        "premiere": "xmeml",
        "kdenlive": "kdenlive",
    }
    requested_formats = {
        format_for_target[target] for target in nle_targets if target in format_for_target
    }
    requested_mp4 = "mp4" in targets
    chosen_extras = extras if extras is not None else nle_extras_from_output(output)

    artifacts: dict[str, Path] = {}
    if nle_targets:
        from videoflow.application.export_service import export_timeline

        artifacts.update(
            export_timeline(
                state,
                exports,
                targets=nle_targets,
                dialect=options.dialect,
                filenames=BUNDLE_FILENAMES,
                extras=chosen_extras,
                progress=progress,
                should_cancel=should_cancel,
                adapter=adapter,
                cache_dir=cache_dir,
            )
        )
        if "kdenlive" in artifacts:
            mlt_path = exports / BUNDLE_FILENAMES["kdenlive_mlt"]
            shutil.copy2(artifacts["kdenlive"], mlt_path)
            artifacts["kdenlive_mlt"] = mlt_path

    mp4_path: Path | None = None
    mp4_report: dict[str, Any] = {"placement": "local", "encoder": "libx264"}
    render_report: dict[str, Any] = {}
    subtitle_path = resolve_subtitle_track(output)
    ass_path = subtitle_path if options.burn_subtitles else None
    final_mix = output / "audio" / "final_mix.wav"
    if requested_mp4 and options.audio_source == "mix" and not final_mix.is_file():
        from videoflow.core.context import PipelineContext
        from videoflow.steps.audio_finalize import (
            AudioFinalizeParams,
            AudioFinalizeStep,
        )
        from videoflow.steps.base import StepIO

        media = state.media_info
        source = Path(media.source_path) if media is not None else output
        context = PipelineContext(
            source=source,
            output=output,
            work=output / "work",
            exports=exports,
            media=media,
            state=state,
        )
        try:
            AudioFinalizeStep().run(
                context,
                AudioFinalizeParams(target_lufs=options.mp4_loudness_lufs),
                StepIO(stage="audio.finalize"),
            )
        except Exception as exc:  # noqa: BLE001 - keep the render fallback explicit
            mp4_report.setdefault("warnings", []).append(
                f"audio.finalize skipped: {exc}"
            )
    if requested_mp4:
        preview = options.mp4_mode == "preview"
        mp4_name = "preview_fast.mp4" if preview else BUNDLE_FILENAMES["mp4"]
        mp4_path = exports / mp4_name
        render_report: dict[str, Any] = {}
        if progress is not None:
            progress("mp4", 0)
        crf = 30 if preview or options.mp4_draft else options.mp4_crf
        preset = (
            "ultrafast"
            if preview
            else ("veryfast" if options.mp4_draft else options.mp4_preset)
        )
        output_fps = 30 if preview else _fps_value(options.mp4_fps)
        audio_bitrate = "128k" if preview else options.mp4_audio_bitrate
        loudness = None if preview else options.mp4_loudness_lufs
        rendered_remote = False
        if (
            options.compute_policy not in {"local", "local_gpu"}
            and not options.mp4_draft
            and not preview
        ):
            try:
                from videoflow.application.compute import (
                    guard_remote_policy,
                    router_from_settings,
                )

                router = router_from_settings()
                guard_remote_policy(
                    router,
                    "render_nvenc",
                    compute_policy=options.compute_policy,
                    allow_slow_cpu_fallback=options.allow_slow_cpu_fallback,
                    error_cls=ExportError,
                )
                health = router.health()
                if not bool(getattr(health, "nvenc", False)):
                    raise ExportError(
                        "worker reports NVENC unavailable: "
                        + (getattr(health, "nvenc_error", "") or "h264_nvenc failed")
                    )
                mezzanine = output / "work" / "bundle_mezzanine.mp4"
                mezzanine.parent.mkdir(parents=True, exist_ok=True)
                if progress is not None:
                    progress("mp4", 10)
                render_master(
                    state,
                    mezzanine,
                    output=output,
                    adapter=adapter,
                    audio_source=options.audio_source,
                    ass_path=None,
                    look=look_from_mapping(output, options.look),
                    crf=18,
                    preset="ultrafast",
                    profile=options.mp4_profile,
                    audio_bitrate=options.mp4_audio_bitrate,
                    loudness_lufs=None,
                    true_peak_db=-2.0,
                    cfr=options.mp4_cfr,
                    fps=output_fps,
                    cache_dir=cache_dir,
                    mode="final",
                )
                params: dict[str, Any] = {
                    "output_name": mp4_path.name,
                    "preset": "p4",
                    "tune": "hq",
                    "cq": 19,
                    "audio_bitrate": "192k",
                }
                if state.media_info is not None:
                    params["width"] = state.media_info.width
                    params["height"] = state.media_info.height
                if output_fps:
                    params["fps"] = output_fps
                inputs = [str(mezzanine)]
                if ass_path is not None:
                    from videoflow.application.remote_fonts import remote_font_paths

                    inputs.append(str(ass_path))
                    fonts = remote_font_paths()
                    if fonts:
                        params["font_paths"] = fonts
                if progress is not None:
                    progress("mp4", 55)
                result = router.submit(
                    "render_nvenc",
                    {"inputs": inputs, "params": params, "timeout_sec": 3600.0},
                    timeout=3600.0,
                )
                remote_path = Path(str(result.get("path") or ""))
                if not remote_path.is_file():
                    raise ExportError("remote NVENC render returned no file")
                mp4_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(remote_path, mp4_path)
                rendered_remote = True
                mp4_report = {
                    "placement": str(result.get("execution_node") or "remote_gpu"),
                    "encoder": "nvenc",
                }
                if progress is not None:
                    progress("mp4", 95)
            except ExportError as exc:
                if (
                    options.compute_policy in {"remote", "remote_only"}
                    and not options.allow_slow_cpu_fallback
                ):
                    raise
                mp4_report["degraded_reason"] = str(exc)
        if not rendered_remote:
            render_master(
                state,
                mp4_path,
                output=output,
                adapter=adapter,
                audio_source=options.audio_source,
                ass_path=ass_path,
                look=look_from_mapping(output, options.look),
                crf=crf,
                preset=preset,
                profile=options.mp4_profile,
                audio_bitrate=audio_bitrate,
                loudness_lufs=loudness,
                true_peak_db=options.mp4_true_peak_db,
                cfr=options.mp4_cfr,
                fps=output_fps,
                progress=((lambda value: progress("mp4", value)) if progress is not None else None),
                cache_dir=cache_dir,
                mode=options.mp4_mode,
                report=render_report,
            )
        artifacts["mp4"] = mp4_path
        mp4_report.update(render_report)
        if progress is not None:
            progress("mp4", 100)

    frames = timeline_frames(state)
    output_fps = 30 if options.mp4_mode == "preview" else _fps_value(options.mp4_fps)
    mp4_frames = (
        round(
            frames
            / (state.media_info.fps_num / state.media_info.fps_den)
            * output_fps
        )
        if output_fps and state.media_info is not None
        else frames
    )
    validation = validate_nle_exports(
        exports,
        timeline_frames=frames,
        blocked_paths=blocked_paths(blockers, output),
        check_media=True,
        formats=requested_formats,
    )
    if mp4_path is not None:
        mp4_dir = _mp4_metadata(mp4_path)
        mp4_ok = bool(mp4_dir.get("exists")) and (
            not mp4_dir.get("duration_frames")
            or abs(int(mp4_dir["duration_frames"]) - mp4_frames) <= 1
        )
        validation["exports"]["mp4"] = {
            "ok": mp4_ok,
            "path": str(mp4_path),
            "errors": [] if mp4_ok else ["mp4 duration does not match the timeline"],
            "warnings": [],
            "mode": options.mp4_mode,
            "encoder": render_report.get("encoder") or video_encoder(),
            "degraded": bool(render_report.get("degraded")),
            "degraded_reason": str(render_report.get("degraded_reason") or ""),
            **mp4_dir,
            **mp4_report,
        }
        validation["ok"] = bool(validation["ok"]) and mp4_ok

    sidecars = _copy_sidecars(output, exports) if options.include_sidecars else []
    files: dict[str, dict[str, object]] = {}
    for name, raw_path in artifacts.items():
        path = Path(raw_path)
        exists = path.is_file()
        files[name] = {
            "path": str(path),
            "sha256": _sha256(path) if exists else "",
            "bytes": path.stat().st_size if exists else 0,
        }
    if "mp4" in files:
        files["mp4"].update(
            {
                "mode": options.mp4_mode,
                "encoder": render_report.get("encoder") or video_encoder(),
                "degraded": bool(render_report.get("degraded")),
                "degraded_reason": str(
                    render_report.get("degraded_reason") or ""
                ),
            }
        )
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "project_id": str(state.project_id),
        "revision": state.revision,
        "timeline_frames": frames,
        "mp4_frames": mp4_frames,
        "targets": list(targets),
        "dialect": options.dialect,
        "mp4": {
            "fps": output_fps or "source",
            "profile": options.mp4_profile,
            "mode": options.mp4_mode,
            "audio_bitrate": (
                "128k" if options.mp4_mode == "preview" else options.mp4_audio_bitrate
            ),
            "loudness_lufs": (
                None if options.mp4_mode == "preview" else options.mp4_loudness_lufs
            ),
            "true_peak_db": options.mp4_true_peak_db,
            "cfr": options.mp4_cfr,
            "audio_source": options.audio_source,
            "encoder": render_report.get("encoder") or video_encoder(),
            "degraded": bool(render_report.get("degraded")),
            "degraded_reason": str(render_report.get("degraded_reason") or ""),
            "audio_master": (
                str(output / "audio" / "master.wav")
                if (output / "audio" / "master.wav").is_file()
                else ""
            ),
            **mp4_report,
        },
        "files": files,
        "sidecars": sidecars,
        "validation": validation,
        "ok": bool(validation.get("ok")),
    }
    manifest_path = exports / BUNDLE_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    if manifest.get("ok"):
        manifest["pruned"] = [str(path) for path in prune_render_segments(output)]
    return manifest


__all__ = [
    "BUNDLE_FILENAME",
    "BUNDLE_FILENAMES",
    "BUNDLE_SCHEMA_VERSION",
    "DEFAULT_BUNDLE_TARGETS",
    "DeliveryBundleRequest",
    "blocked_paths",
    "build_delivery_bundle",
    "timeline_frames",
]
