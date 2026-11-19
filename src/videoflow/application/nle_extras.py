"""Build native NLE finishing inputs from one job output directory."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from videoflow.application.timeline_meta import load_meta
from videoflow.exporters.extras import (
    NleAdjustment,
    NleBroll,
    NleExtras,
    NleMarker,
    NleMusic,
    NleTitle,
)

ASS_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")


def _seconds(value: str) -> float:
    match = ASS_TIME.match(value.strip())
    if match is None:
        return 0.0
    hours, minutes, seconds, centis = (int(item) for item in match.groups())
    return hours * 3600 + minutes * 60 + seconds + centis / 100


def _titles(path: Path) -> tuple[NleTitle, ...]:
    if not path.is_file():
        return ()
    titles: list[NleTitle] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        text = re.sub(r"\{[^}]*\}", "", parts[9]).strip()
        if not text:
            continue
        titles.append(
            NleTitle(
                text=text,
                start_sec=_seconds(parts[1]),
                end_sec=_seconds(parts[2]),
                kind="title",
            )
        )
    return tuple(titles)


def _captions(directory: Path) -> tuple[NleTitle, ...]:
    """Read the long-form caption sidecar without duplicating merged titles."""

    for relative in ("captions/captions.ass", "captions.ass"):
        path = Path(directory) / relative
        if not path.is_file():
            continue
        return tuple(replace(title, kind="caption") for title in _titles(path))
    return ()


def _filters(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(str(item) for item in payload.get("filters", []) if str(item))


def _broll(output: Path) -> tuple[NleBroll, ...]:
    for name in ("broll-matches.json", "broll.json"):
        path = output / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        plan = payload.get("shorts", payload) if isinstance(payload, dict) else {}
        entries: list[NleBroll] = []
        for cues in plan.values() if isinstance(plan, dict) else []:
            for cue in cues if isinstance(cues, list) else []:
                if not isinstance(cue, dict) or not cue.get("path"):
                    continue
                entries.append(
                    NleBroll(
                        path=str(cue["path"]),
                        start_sec=float(cue.get("start_sec") or 0.0),
                        duration_sec=float(cue.get("duration_sec") or 2.0),
                        name=Path(str(cue["path"])).stem,
                    )
                )
        if entries:
            return tuple(entries)
    return ()


def _project_overlays(directory: Path) -> tuple[NleBroll, ...]:
    path = directory / "project_state.json"
    if not path.is_file():
        return ()
    try:
        import json as _json

        payload = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    media = payload.get("media_info") or {}
    fps_num = float(media.get("fps_num") or 30)
    fps_den = float(media.get("fps_den") or 1)
    fps = fps_num / max(0.001, fps_den)
    canvas_w = int(media.get("width") or 0)
    canvas_h = int(media.get("height") or 0)
    entries: list[NleBroll] = []
    for overlay in payload.get("overlays", []):
        if not isinstance(overlay, dict) or not overlay.get("path"):
            continue
        from videoflow.application.alpha_media import prepare_prores_overlay
        from videoflow.application.overlay_geometry import asset_dimensions, overlay_box
        from videoflow.domain.state import OverlayClip

        try:
            clip = OverlayClip.model_validate(overlay)
            box = overlay_box(clip, canvas_w, canvas_h) if canvas_w and canvas_h else None
            source_path = prepare_prores_overlay(Path(clip.path), cache_dir=directory / ".alpha")
            source_w, source_h = asset_dimensions(source_path, clip.kind)
        except Exception:  # noqa: BLE001 - keep the NLE export usable without geometry
            clip = None
            box = None
            source_path = Path(str(overlay["path"]))
            source_w = source_h = 0
        entries.append(
            NleBroll(
                path=str(source_path),
                start_sec=float(overlay.get("start_frame") or 0) / fps,
                duration_sec=max(0.1, float(overlay.get("duration_frames") or 1) / fps),
                name=Path(str(overlay["path"])).stem,
                kind=str(overlay.get("kind") or "image"),
                anchor=str(overlay.get("anchor") or "top_center"),
                margin_x=int(overlay.get("margin_x") or 0),
                margin_y=int(overlay.get("margin_y") or 0),
                width_ratio=float(overlay.get("width_ratio") or 1.0),
                opacity=float(overlay.get("opacity") or 1.0),
                z=int(overlay.get("z") or 20),
                x=box.x if box is not None else 0,
                y=box.y if box is not None else 0,
                width=box.width if box is not None else 0,
                height=box.height if box is not None else 0,
                source_width=source_w,
                source_height=source_h,
            )
        )
    return tuple(entries)


def _timeline_fps(directory: Path) -> float:
    path = Path(directory) / "project_state.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        media = payload.get("media_info") or {}
        try:
            return float(media.get("fps_num") or 30) / max(1.0, float(media.get("fps_den") or 1))
        except ValueError:
            return 30.0
    return 30.0


def _duck_ranges(directory: Path) -> tuple[tuple[float, float, float], ...]:
    path = Path(directory) / "audio" / "ducking.json"
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    ranges: list[tuple[float, float, float]] = []
    for item in payload.get("ducking", []):
        if not isinstance(item, dict):
            continue
        start = float(item.get("start_sec") or 0.0)
        end = float(item.get("end_sec") or start)
        if end > start:
            ranges.append((start, end, float(item.get("level_db") or -12.0)))
    return tuple(sorted(ranges))


def _music(directory: Path) -> tuple[NleMusic, ...]:
    path = Path(directory) / "audio" / "beatmap.json"
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    fps = _timeline_fps(directory)
    ducking = _duck_ranges(directory)
    tracks: list[NleMusic] = []
    for item in payload.get("music_tracks", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        start = float(item.get("start_frame") or 0.0) / fps
        end_frame = float(item.get("end_frame") or 0.0)
        duration = (end_frame / fps - start) if end_frame > 0 else 0.0
        ranges = ducking if item.get("duck_under_speech", True) else ()
        tracks.append(
            NleMusic(
                path=str(item["path"]),
                start_sec=max(0.0, start),
                duration_sec=max(0.1, duration or 60.0),
                gain_db=float(item.get("gain_db") or -18.0),
                duck_ranges=tuple(ranges),
            )
        )
    return tuple(tracks)


def _motion(directory: Path) -> tuple[NleBroll, ...]:
    entries: list[NleBroll] = []
    manifest = directory / "motion" / "render-manifest.json"
    if manifest.is_file():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        for scene in payload.get("scenes", []) if isinstance(payload, dict) else []:
            if not isinstance(scene, dict) or not scene.get("path"):
                continue
            path = Path(str(scene["path"]))
            if not path.is_file():
                continue
            entries.append(
                NleBroll(
                    path=str(path),
                    start_sec=float(scene.get("start_sec") or 0.0),
                    duration_sec=float(scene.get("duration_sec") or 1.0),
                    name=str(scene.get("scene_id") or path.stem),
                    kind="video",
                )
            )
    intro = directory / "motion" / "intro.json"
    if intro.is_file():
        try:
            payload = json.loads(intro.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        path = Path(str(payload.get("path") or "")) if isinstance(payload, dict) else Path()
        if path.is_file():
            entries.append(
                NleBroll(
                    path=str(path),
                    start_sec=0.0,
                    duration_sec=float(payload.get("duration_sec") or 1.0),
                    name="intro",
                    kind="video",
                )
            )
    return tuple(entries)


def nle_extras_from_output(output: Path) -> NleExtras:
    """Read markers, titles, B-roll, colour, and the audio master if present."""

    directory = Path(output)
    meta = load_meta(directory)
    markers = [
        NleMarker(
            name=item.label or item.id,
            start_sec=item.time_sec,
            end_sec=getattr(item, "end_sec", 0.0),
            note=item.color,
            color=item.color,
        )
        for item in meta.markers
    ]
    chapters = directory / "chapters.json"
    if chapters.is_file():
        try:
            payload = json.loads(chapters.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        for chapter in payload.get("chapters", []):
            if not isinstance(chapter, dict) or chapter.get("start_sec") is None:
                continue
            markers.append(
                NleMarker(
                    name=str(chapter.get("title") or "Chapter"),
                    start_sec=float(chapter["start_sec"]),
                    note="chapter",
                    color="#22c55e",
                )
            )
    markers.sort(key=lambda item: item.start_sec)
    stems = directory / "audio" / "master.wav"
    colors = _filters(directory / "color" / "filters.json")
    audio = _filters(directory / "audio" / "master-filters.json")
    adjustments: list[NleAdjustment] = []
    adjustment_path = directory / "exports" / "adjustment_layers.json"
    if adjustment_path.is_file():
        try:
            payload = json.loads(adjustment_path.read_text(encoding="utf-8"))
            for item in payload.get("layers", []):
                adjustments.append(
                    NleAdjustment(
                        name=str(item.get("name") or "Adjustment"),
                        start_sec=float(item.get("start_sec") or 0.0),
                        end_sec=float(item.get("end_sec") or 0.0),
                        lut_path=str(item.get("lut_path") or ""),
                        grain_amount=float(item.get("grain_amount") or 0.0),
                        grain_fps=float(item.get("grain_fps") or 12.0),
                    )
                )
        except (OSError, ValueError, TypeError):
            adjustments = []
    return NleExtras(
        markers=markers,
        titles=_titles(directory / "titles.ass"),
        broll=_broll(directory) + _project_overlays(directory) + _motion(directory),
        color_filters=colors,
        audio_filters=audio,
        audio_stem=str(stems) if stems.is_file() else "",
        adjustments=tuple(adjustments),
        music=_music(directory),
        captions=_captions(directory),
    )
