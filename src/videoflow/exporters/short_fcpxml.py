"""FCPXML handoff for dynamic Shorts: V1 base, V2 face, A1 voice, A2 SFX."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote, urlparse

from videoflow.application.short_composition.geometry import CanvasRegion
from videoflow.domain.short_composition import ShortCompositionPlan
from videoflow.exporters.common import file_uri, write_text, xml_document

FCPXML_VERSION = "1.10"


@dataclass(frozen=True, slots=True)
class FaceClip:
    seg_id: str
    path: Path
    offset_sec: float
    duration_sec: float
    panel: CanvasRegion


@dataclass(frozen=True, slots=True)
class SfxClip:
    path: Path
    offset_sec: float
    duration_sec: float = 1.0


@dataclass(frozen=True, slots=True)
class CaptionClip:
    start_sec: float
    end_sec: float
    text: str
    subtitle_y: int


def _sec(value: float) -> Fraction:
    return Fraction(str(max(0.0, float(value)))).limit_denominator(1_000_000)


def _rt(value: float) -> str:
    return f"{_sec(value).numerator}/{_sec(value).denominator}s"


def _asset(
    resources: ET.Element,
    *,
    asset_id: str,
    path: Path,
    duration_sec: float,
    has_video: bool,
    has_audio: bool,
    name: str = "",
) -> None:
    attrs = {
        "id": asset_id,
        "name": name or Path(path).name,
        "start": "0s",
        "duration": _rt(duration_sec),
        "hasVideo": "1" if has_video else "0",
        "videoSources": "1" if has_video else "0",
        "hasAudio": "1" if has_audio else "0",
        "format": "r1",
    }
    if has_audio:
        attrs.update({"audioSources": "1", "audioChannels": "1", "audioRate": "48000"})
    asset = ET.SubElement(resources, "asset", attrs)
    ET.SubElement(
        asset,
        "media-rep",
        {"kind": "original-media", "src": file_uri(path)},
    )


def export_short_fcpxml(
    plan: ShortCompositionPlan,
    output_path: Path,
    *,
    final_video: Path,
    source: Path,
    face_clips: Sequence[FaceClip] = (),
    sfx: Sequence[SfxClip] = (),
    captions: Sequence[CaptionClip] = (),
    source_duration: float = 0.0,
    duration_sec: float = 0.0,
    fps: int = 30,
    dialect: str = FCPXML_VERSION,
) -> Path:
    """Write an editable FCPXML with explicit V1/V2/A1/A2 lanes."""

    if dialect not in {"1.9", "1.10"}:
        raise ValueError(f"Unsupported FCPXML dialect: {dialect}")
    duration = max(0.1, float(duration_sec or plan.duration_sec + 0.35))
    source_duration = max(duration, float(source_duration or duration))
    root = ET.Element("fcpxml", {"version": dialect})
    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources,
        "format",
        {
            "id": "r1",
            "name": f"FFVideoFormat1080x1920p{int(fps)}",
            "width": "1080",
            "height": "1920",
            "frameDuration": _rt(1.0 / max(1, int(fps))),
        },
    )
    _asset(
        resources,
        asset_id="r2",
        path=final_video,
        duration_sec=duration,
        has_video=True,
        has_audio=True,
        name=f"{plan.short_id} base",
    )
    _asset(
        resources,
        asset_id="a1",
        path=source,
        duration_sec=source_duration,
        has_video=True,
        has_audio=True,
        name="Source",
    )
    face_ids: dict[int, str] = {}
    for index, clip in enumerate(face_clips, start=1):
        asset_id = f"f{index}"
        face_ids[index] = asset_id
        _asset(
            resources,
            asset_id=asset_id,
            path=clip.path,
            duration_sec=max(0.05, clip.duration_sec),
            has_video=True,
            has_audio=False,
            name=f"Face {clip.seg_id}",
        )
    sfx_ids: dict[int, str] = {}
    for index, clip in enumerate(sfx, start=1):
        asset_id = f"s{index}"
        sfx_ids[index] = asset_id
        _asset(
            resources,
            asset_id=asset_id,
            path=clip.path,
            duration_sec=max(0.05, clip.duration_sec),
            has_video=False,
            has_audio=True,
            name=f"SFX {Path(clip.path).stem}",
        )
    ET.SubElement(
        resources,
        "effect",
        {
            "id": "r3",
            "name": "Basic Title",
            "uid": (
                ".../Titles.localized/Bumper:Opener.localized/"
                "Basic Title.localized/Basic Title.moti"
            ),
        },
    )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": "VideoFlow Shorts"})
    project = ET.SubElement(event, "project", {"name": plan.short_id})
    sequence = ET.SubElement(
        project,
        "sequence",
        {
            "format": "r1",
            "duration": _rt(duration),
            "tcStart": "0s",
            "tcFormat": "NDF",
            "audioLayout": "stereo",
            "audioRate": "48k",
        },
    )
    spine = ET.SubElement(sequence, "spine")
    ET.SubElement(
        spine,
        "asset-clip",
        {
            "ref": "r2",
            "name": "V1 base",
            "offset": "0s",
            "start": "0s",
            "duration": _rt(duration),
            "srcEnable": "video",
            "videoRole": "base",
        },
    )
    for index, clip in enumerate(face_clips, start=1):
        element = ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": face_ids[index],
                "lane": "1",
                "name": f"V2 face {clip.seg_id}",
                "offset": _rt(clip.offset_sec),
                "start": "0s",
                "duration": _rt(clip.duration_sec),
                "srcEnable": "video",
                "videoRole": "face",
            },
        )
        position_x = round(clip.panel.center_x - 540.0, 3)
        position_y = round(960.0 - clip.panel.center_y, 3)
        ET.SubElement(
            element,
            "adjust-transform",
            {
                "position": f"{position_x:g} {position_y:g}",
                "scale": "1 1",
                "anchor": "0 0",
            },
        )
    for segment in plan.segments:
        ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": "a1",
                "lane": "-1",
                "name": f"A1 voice {segment.seg_id}",
                "offset": _rt(segment.rel_start),
                "start": _rt(plan.start + segment.rel_start),
                "audioStart": _rt(plan.start + segment.rel_start),
                "duration": _rt(segment.rel_end - segment.rel_start),
                "audioDuration": _rt(segment.rel_end - segment.rel_start),
                "srcEnable": "audio",
                "audioRole": "dialogue",
            },
        )
    for index, clip in enumerate(sfx, start=1):
        ET.SubElement(
            spine,
            "asset-clip",
            {
                "ref": sfx_ids[index],
                "lane": "-2",
                "name": f"A2 SFX {Path(clip.path).stem}",
                "offset": _rt(clip.offset_sec),
                "start": "0s",
                "duration": _rt(clip.duration_sec),
                "srcEnable": "audio",
                "audioRole": "effects",
            },
        )
    for index, caption in enumerate(captions, start=1):
        element = ET.SubElement(
            spine,
            "title",
            {
                "ref": "r3",
                "lane": "6",
                "name": f"Caption {index}",
                "offset": _rt(caption.start_sec),
                "duration": _rt(max(0.1, caption.end_sec - caption.start_sec)),
            },
        )
        text = ET.SubElement(element, "text")
        ET.SubElement(text, "text-style", {"ref": f"cs{index}"}).text = caption.text
        definition = ET.SubElement(element, "text-style-def", {"id": f"cs{index}"})
        ET.SubElement(
            definition,
            "text-style",
            {
                "font": "Helvetica",
                "fontSize": "64",
                "fontColor": "1 1 1 1",
                "alignment": "center",
            },
        )
        position_y = 960.0 - caption.subtitle_y
        ET.SubElement(
            element,
            "adjust-transform",
            {"position": f"0 {position_y:g}", "scale": "1 1", "anchor": "0 0"},
        )
    for index, segment in enumerate(plan.segments[1:], start=1):
        ET.SubElement(
            sequence,
            "marker",
            {
                "start": _rt(segment.rel_start),
                "duration": "0s",
                "value": f"Layout {segment.layout}",
                "note": f"{index + 1}/{len(plan.segments)}",
            },
        )
    return write_text(output_path, xml_document(root, "fcpxml"))


def validate_short_fcpxml(
    path: Path,
    *,
    check_media: bool = True,
    require_tracks: Sequence[str] = ("0", "1", "-1", "-2"),
) -> dict[str, object]:
    """Smoke-check structure, lanes, and media references without Resolve."""

    target = Path(path)
    try:
        root = ET.parse(target).getroot()
    except (OSError, ET.ParseError) as exc:
        return {"ok": False, "errors": [f"invalid FCPXML: {exc}"], "warnings": []}
    errors: list[str] = []
    warnings: list[str] = []
    if root.tag != "fcpxml":
        errors.append("root element is not fcpxml")
    if root.get("version") not in {"1.9", "1.10"}:
        errors.append(f"unsupported FCPXML version: {root.get('version')}")
    sequence = root.find(".//sequence")
    if sequence is None:
        errors.append("sequence is missing")
        return {"ok": False, "errors": errors, "warnings": warnings}
    spine = sequence.find("spine")
    if spine is None:
        errors.append("spine is missing")
        return {"ok": False, "errors": errors, "warnings": warnings}
    lanes = {clip.get("lane", "0") for clip in spine}
    missing = set(require_tracks) - lanes
    if missing:
        errors.append(f"missing expected lanes: {sorted(missing)}")
    media: set[Path] = set()
    for element in root.findall(".//media-rep"):
        src = element.get("src") or ""
        parsed = urlparse(src)
        if parsed.scheme != "file":
            errors.append(f"unsupported media URI: {src[:120]}")
            continue
        media_path = Path(unquote(parsed.path))
        media.add(media_path)
        if check_media and not media_path.is_file():
            errors.append(f"offline media: {media_path}")
    if not media:
        errors.append("no media references found")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "version": root.get("version"),
        "lanes": sorted(lanes),
        "media_count": len(media),
        "media": sorted(str(item) for item in media),
        "duration": sequence.get("duration", ""),
    }


def write_short_export_report(path: Path, payload: dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "CaptionClip",
    "FCPXML_VERSION",
    "FaceClip",
    "SfxClip",
    "export_short_fcpxml",
    "generate_face_clips",
    "validate_short_fcpxml",
    "write_short_export_report",
]


def generate_face_clips(
    renders: Sequence[object],
    source: Path,
    directory: Path,
    *,
    fps: int = 30,
    force: bool = False,
    ffmpeg: str = "ffmpeg",
    offset_base: float = 0.0,
    check_cancel: Callable[[], None] | None = None,
) -> tuple[list[FaceClip], list[str]]:
    """Render one face-panel clip per segment for the V2 track."""

    import subprocess

    from videoflow.application.short_composition.geometry import layout_geometry

    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    clips: list[FaceClip] = []
    warnings: list[str] = []
    for index, render in enumerate(renders, start=1):
        if check_cancel is not None:
            check_cancel()
        panel = layout_geometry(str(render.layout)).face
        path = target_dir / f"face_{index:04d}.mp4"
        if not force and path.is_file() and path.stat().st_size > 0:
            clips.append(
                FaceClip(
                    seg_id=str(render.seg_id),
                    path=path,
                    offset_sec=max(0.0, float(render.source_start)),
                    duration_sec=float(render.duration),
                    panel=panel,
                )
            )
            continue
        crop = render.face_crop
        width = max(2, int(panel.width) - int(panel.width) % 2)
        height = max(2, int(panel.height) - int(panel.height) % 2)
        crop_w = max(2, int(crop.width) - int(crop.width) % 2)
        crop_h = max(2, int(crop.height) - int(crop.height) % 2)
        argv = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{float(render.source_start):.6f}",
            "-t",
            f"{float(render.duration):.6f}",
            "-i",
            str(source),
            "-vf",
            f"crop={crop_w}:{crop_h}:{int(crop.x)}:{int(crop.y)},"
            f"scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-r",
            str(int(fps)),
            str(path),
        ]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            warnings.append(
                f"Face track {render.seg_id} failed: {exc}"
            )
            continue
        if completed.returncode != 0 or not path.is_file():
            tail = (completed.stderr or "").strip().splitlines()
            warnings.append(
                f"Face track {render.seg_id} failed: "
                + (tail[-1][:300] if tail else "no output")
            )
            continue
        clips.append(
            FaceClip(
                seg_id=str(render.seg_id),
                path=path,
                offset_sec=max(0.0, float(render.source_start)),
                duration_sec=float(render.duration),
                panel=panel,
            )
        )
    return clips, warnings
