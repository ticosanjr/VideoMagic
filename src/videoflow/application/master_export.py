"""Canonical MP4 master renderer shared by video export and delivery bundles."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from videoflow.exporters.mp4 import (
    DEFAULT_AUDIO_BITRATE,
    PREVIEW_MAX_SCALE,
    YOUTUBE_LUFS,
    ExportMode,
    export_mp4,
    video_encoder,
)


@dataclass(frozen=True, slots=True)
class MasterLook:
    """Color, LUT, grain, and audio finishing for one master."""

    lut_path: str = ""
    grain_amount: float = 0.0
    grain_fps: float = 12.0
    video_filters: tuple[str, ...] = ()
    audio_filters: tuple[str, ...] = ()


def project_look(output: Path) -> MasterLook:
    from videoflow.application.render_inputs import read_filters

    root = Path(output).expanduser()
    return MasterLook(
        video_filters=tuple(read_filters(root / "color" / "filters.json")),
        audio_filters=tuple(read_filters(root / "audio" / "master-filters.json")),
    )


def look_from_mapping(output: Path, look: dict[str, Any] | None) -> MasterLook:
    base = project_look(output)
    if not look:
        return base
    lut_path = (
        str(look.get("lut_path"))
        if look.get("lut_path") is not None
        else base.lut_path
    )
    grain = (
        float(look.get("grain_amount"))
        if look.get("grain_amount") is not None
        else base.grain_amount
    )
    grain_fps = (
        float(look.get("grain_fps"))
        if look.get("grain_fps") is not None
        else base.grain_fps
    )
    video_filters = look.get("video_filters")
    audio_filters = look.get("audio_filters")
    return replace(
        base,
        lut_path=lut_path,
        grain_amount=max(0.0, min(1.0, grain)),
        grain_fps=max(1.0, min(60.0, grain_fps)),
        video_filters=(
            tuple(str(item) for item in video_filters)
            if isinstance(video_filters, list)
            else base.video_filters
        ),
        audio_filters=(
            tuple(str(item) for item in audio_filters)
            if isinstance(audio_filters, list)
            else base.audio_filters
        ),
    )


def _look_filters(output: Path, look: MasterLook) -> list[str]:
    filters = [item for item in look.video_filters if item]
    if look.lut_path:
        lut = Path(look.lut_path).expanduser()
        if not lut.is_absolute():
            lut = Path(output).expanduser() / lut
        if lut.is_file():
            escaped = str(lut).replace("'", "'")
            filters.append(f"lut3d=file='{escaped}':interp=tetrahedral")
    if look.grain_amount > 0:
        strength = max(1, min(20, int(look.grain_amount * 20)))
        filters.append(f"noise=alls={strength}:allf=t+u")
    return filters


def resolve_render_profile(
    state: Any,
    *,
    mode: ExportMode = "final",
    fps: int | None = None,
    draft: bool = False,
    draft_scale: float = 1.0,
) -> dict[str, Any]:
    """Resolve preview/final fps, scale, bitrate, and QA precedence once."""

    media = getattr(state, "media_info", None)
    if mode == "preview":
        return {
            "mode": "preview",
            "fps": 30,
            "scale_height": None,
            "scale_max": PREVIEW_MAX_SCALE,
            "audio_bitrate": "128k",
            "loudness_lufs": None,
            "qa_mode": "off",
            "cfr": True,
        }
    scale_height = None
    if draft and media is not None and 0 < float(draft_scale) < 1:
        scale_height = max(144, int(round(media.height * float(draft_scale))))
    return {
        "mode": "final",
        "fps": int(fps) if fps and int(fps) > 0 else None,
        "scale_height": scale_height,
        "scale_max": None,
        "audio_bitrate": None,
        "loudness_lufs": None,
        "qa_mode": None,
        "cfr": False,
    }


def _is_explicit_audio_source(output: Path, audio_source: str) -> bool:
    token = str(audio_source or "").strip()
    if token in {"", "timeline", "mix", "final", "final_mix", "master"}:
        return False
    candidate = Path(token).expanduser()
    if not candidate.is_absolute():
        candidate = Path(output).expanduser() / candidate
    return candidate.is_file()


def resolve_audio_master(output: Path, audio_source: str) -> Path | None:
    """Resolve timeline, final mix, master, or an explicit audio path."""

    root = Path(output).expanduser()
    source = str(audio_source or "").strip()
    if source in {"", "timeline"}:
        return None
    if source in {"mix", "final", "final_mix"}:
        for candidate in (
            root / "audio" / "final_mix.wav",
            root / "audio" / "final.wav",
            root / "audio" / "master.wav",
        ):
            if candidate.is_file():
                return candidate
        return None
    if source == "master":
        master = root / "audio" / "master.wav"
        return master if master.is_file() else None
    explicit = Path(source).expanduser()
    if not explicit.is_absolute():
        explicit = root / explicit
    return explicit if explicit.is_file() else None


def render_master(
    state: Any,
    destination: Path,
    *,
    output: Path,
    adapter: Any | None = None,
    audio_source: str = "master",
    ass_path: Path | None = None,
    burn_subtitles: bool | None = None,
    qa_mode: str = "fast",
    look: MasterLook | None = None,
    crf: int = 18,
    preset: str = "medium",
    profile: str = "",
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    loudness_lufs: float | None = YOUTUBE_LUFS,
    true_peak_db: float = -2.0,
    cfr: bool = False,
    progress: Callable[[int], None] | None = None,
    scale_height: int | None = None,
    cache_dir: Path | None = None,
    video_filters: Sequence[str] | None = None,
    fps: int | None = None,
    mode: ExportMode = "final",
    draft: bool = False,
    draft_scale: float = 1.0,
    report: dict[str, Any] | None = None,
) -> Path:
    """Render one timeline to the same H.264/AAC master for every caller."""

    outcome = report if report is not None else {}
    outcome.setdefault("encoder", video_encoder())
    outcome.setdefault("degraded", False)
    profile = resolve_render_profile(
        state,
        mode=mode,
        fps=fps,
        draft=draft,
        draft_scale=draft_scale,
    )
    mode = profile["mode"]
    if profile["fps"] is not None:
        fps = int(profile["fps"])
    if profile["scale_height"] is not None:
        scale_height = int(profile["scale_height"])
    scale_max = profile["scale_max"]
    if profile["audio_bitrate"] is not None:
        audio_bitrate = str(profile["audio_bitrate"])
    if profile["loudness_lufs"] is not None or mode == "preview":
        loudness_lufs = profile["loudness_lufs"]
    if profile["qa_mode"] is not None:
        qa_mode = str(profile["qa_mode"])
    cfr = bool(profile["cfr"]) or cfr
    chosen = look or project_look(output)
    final_mix = Path(output).expanduser() / "audio" / "final_mix.wav"
    explicit_audio = _is_explicit_audio_source(output, audio_source)
    if mode in {"preview", "final"} and final_mix.is_file() and not explicit_audio:
        audio_master = final_mix
        audio_source = "final_mix"
    else:
        audio_master = resolve_audio_master(output, audio_source)
    outcome["audio_source"] = audio_source
    outcome["audio_master"] = str(audio_master) if audio_master else ""
    filters = list(_look_filters(output, chosen))
    if video_filters:
        filters.extend(str(item) for item in video_filters if item)
    return export_mp4(
        state,
        destination,
        adapter=adapter,
        crf=crf,
        preset=preset,
        profile=profile,
        audio_bitrate=audio_bitrate,
        loudness_lufs=loudness_lufs,
        true_peak_db=true_peak_db,
        cfr=cfr,
        audio_master=audio_master,
        audio_filters=list(chosen.audio_filters),
        video_filters=filters,
        ass_path=ass_path,
        burn_subtitles=burn_subtitles,
        qa_mode=qa_mode,
        progress=progress,
        scale_height=scale_height,
        scale_max=scale_max,
        cache_dir=cache_dir,
        fps=fps,
        mode=mode,
        report=outcome,
    )


__all__ = [
    "MasterLook",
    "look_from_mapping",
    "project_look",
    "render_master",
    "resolve_audio_master",
    "resolve_render_profile",
]
