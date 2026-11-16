"""Structural validation for the XML NLE exports."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _resolve_export_path(
    directory: Path,
    extension: str,
    fixed_name: str,
) -> Path:
    """Prefer the fixed legacy name, then the newest timestamped export."""

    fixed = directory / fixed_name
    if fixed.is_file():
        return fixed
    candidates = [
        path for path in directory.glob(f"*{extension}") if "_VideoFlow_Edited_" in path.name
    ]
    if not candidates:
        candidates = list(directory.glob(f"*{extension}"))
    if not candidates:
        return fixed
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def validate_nle_exports(
    directory: Path,
    *,
    timeline_frames: int | None = None,
    blocked_paths: set[str] | None = None,
    check_media: bool = False,
) -> dict[str, Any]:
    """Validate the NLE documents, optionally against the source timeline.

    ``check_media`` resolves every referenced file and fails when it is missing
    or belongs to a license-blocked asset. ``timeline_frames`` additionally
    compares each document duration with the master timeline.
    """

    directory = Path(directory).expanduser()
    blocked = {_normalize_path(item) for item in (blocked_paths or set()) if str(item).strip()}
    checks: dict[str, dict[str, Any]] = {}
    for name, extension, validator in (
        ("fcpxml", ".fcpxml", _validate_fcpxml),
        ("xmeml", ".xml", _validate_xmeml),
        ("kdenlive", ".kdenlive", _validate_kdenlive),
    ):
        fixed_name = "timeline.xml" if name == "xmeml" else f"timeline.{name}"
        path = _resolve_export_path(directory, extension, fixed_name)
        result = validator(path)
        result["nle"] = name
        if check_media and result.get("ok"):
            _apply_media_checks(result, blocked)
        if timeline_frames is not None and result.get("ok"):
            _apply_duration_check(result, timeline_frames)
        checks[name] = result
    ok = all(item["ok"] for item in checks.values())
    return {"ok": ok, "directory": str(directory), "exports": checks}


def _normalize_path(value: str | Path) -> str:
    text = str(value).strip()
    if not text:
        return ""
    try:
        return str(Path(text).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return text


def _uri_to_path(value: str) -> Path | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.startswith("file:"):
        parsed = urlparse(raw)
        path = unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc != "localhost":
            path = f"//{parsed.netloc}{path}"
        if len(path) > 2 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path) if path else None
    if "://" in raw:
        return None
    return Path(raw)


def _references(root: ET.Element, nle: str) -> list[str]:
    values: list[str] = []
    if nle == "fcpxml":
        values.extend(item.get("src", "") for item in root.findall("./resources/asset/media-rep"))
    elif nle == "xmeml":
        values.extend(item.text or "" for item in root.findall(".//file/pathurl"))
    else:
        for node in root.findall("./chain") + root.findall("./producer"):
            for prop in node.findall("property"):
                if prop.get("name") == "resource" and prop.text:
                    if prop.text.strip() in {"black", "color:black"}:
                        continue
                    values.append(prop.text)
    return [value for value in values if value.strip()]


def _resolve_references(root: ET.Element, nle: str) -> list[Path]:
    resolved: list[Path] = []
    for value in _references(root, nle):
        path = _uri_to_path(value)
        if path is not None:
            resolved.append(path)
    return resolved


def _apply_media_checks(result: dict[str, Any], blocked: set[str]) -> None:
    path = Path(result.get("path", ""))
    root = ET.parse(path).getroot()
    references = _resolve_references(root, result["nle"])
    missing = sorted(
        {str(item) for item in references if not item.is_file()},
    )
    blocked_names = {
        Path(value).name for value in blocked if "/" not in value and "\\" not in value
    }
    blocked_refs = sorted(
        {
            str(item)
            for item in references
            if _normalize_path(item) in blocked or Path(item).name in blocked_names
        }
    )
    result["media"] = {
        "references": len(references),
        "missing": missing,
        "blocked": blocked_refs,
    }
    if missing:
        result["errors"].append(f"missing media: {', '.join(missing[:6])}")
    if blocked_refs:
        result["errors"].append(f"license-blocked media: {', '.join(blocked_refs[:6])}")
    result["ok"] = not result["errors"] and path.is_file()


def _apply_duration_check(result: dict[str, Any], expected: int) -> None:
    path = Path(result.get("path", ""))
    root = ET.parse(path).getroot()
    actual = _document_frames(root, result["nle"])
    result["duration"] = {"expected_frames": expected, "actual_frames": actual}
    if actual is None:
        result["warnings"].append("could not read the exported duration")
        return
    if abs(actual - expected) > 1:
        result["errors"].append(f"duration mismatch: timeline {expected} frames, export {actual}")
        result["ok"] = False
    result["duration"]["ok"] = abs(actual - expected) <= 1


def _document_frames(root: ET.Element, nle: str) -> int | None:
    if nle == "fcpxml":
        sequence = root.find("./library/event/project/sequence")
        if sequence is None:
            return None
        seconds = _rational_seconds(sequence.get("duration", ""))
        rate = root.find("./resources/format")
        fps = 30.0
        if rate is not None:
            frames = _rational_fraction(rate.get("frameDuration", ""))
            if frames and frames > 0:
                fps = float(1 / frames)
        return round(seconds * fps) if seconds else None
    if nle == "xmeml":
        raw = root.findtext("./sequence/duration")
        try:
            return int(float(raw or 0))
        except ValueError:
            return None
    profile = root.find("profile")
    tractor = next(
        (
            item
            for item in root.findall("tractor")
            if any(
                prop.get("name") == "kdenlive:projectTractor" for prop in item.findall("property")
            )
        ),
        None,
    )
    if tractor is None:
        return None
    out = tractor.get("out", "")
    if profile is not None:
        try:
            fps = float(profile.get("frame_rate_num", "30")) / float(
                profile.get("frame_rate_den", "1")
            )
        except ValueError:
            fps = 30.0
    else:
        fps = 30.0
    return round(_timecode_seconds(out) * fps)


def _rational_fraction(value: str) -> Fraction | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("s"):
        raw = raw[:-1]
    try:
        return Fraction(raw)
    except (ValueError, ZeroDivisionError):
        return None


def _rational_seconds(value: str) -> float:
    fraction = _rational_fraction(value)
    return float(fraction) if fraction is not None else 0.0


def _timecode_seconds(value: str) -> float:
    raw = (value or "").strip()
    if not raw:
        return 0.0
    if ":" not in raw:
        return _rational_seconds(raw)
    total = 0.0
    for part in raw.split(":"):
        try:
            total = total * 60 + float(part.replace(",", "."))
        except ValueError:
            return 0.0
    return total


def _result(
    path: Path,
    errors: list[str],
    *,
    warnings: list[str] | None = None,
    **details: Any,
) -> dict[str, Any]:
    return {
        "ok": not errors and path.is_file(),
        "path": str(path),
        "errors": errors,
        "warnings": list(warnings or []),
        **details,
    }


def _validate_fcpxml(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return _result(path, ["missing file"])
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return _result(path, [f"parse error: {exc}"])
    if root.tag != "fcpxml":
        errors.append("root is not fcpxml")
    clips = root.findall("./library/event/project/sequence/spine/asset-clip")
    if not clips:
        errors.append("no asset-clip in sequence spine")
    if not root.findall("./resources/asset/media-rep"):
        errors.append("asset has no media-rep")
    transitions = root.findall("./library/event/project/sequence/spine/transition")
    keyframes = root.findall(".//adjust-transform//keyframe")
    if not transitions:
        warnings.append("no transition elements")
    if not keyframes:
        warnings.append("no transform keyframes")
    if len(clips) > 1 and len(transitions) < len(clips) - 1:
        warnings.append("some joins have no transition")
    titles = root.findall("./library/event/project/sequence/spine/title")
    markers = root.findall("./library/event/project/sequence/marker")
    filters = root.findall("./library/event/project/sequence/spine/asset-clip/filter-video")
    broll = root.findall("./library/event/project/sequence/spine/asset-clip[@lane='2']")
    stems = root.findall("./library/event/project/sequence/spine/asset-clip[@lane='4']")
    return _result(
        path,
        errors,
        warnings=warnings,
        clips=len(clips),
        transitions=len(transitions),
        keyframes=len(keyframes),
        titles=len(titles),
        markers=len(markers),
        color_filters=len(filters),
        broll_clips=len(broll),
        audio_stems=len(stems),
    )


def _validate_xmeml(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return _result(path, ["missing file"])
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return _result(path, [f"parse error: {exc}"])
    if root.tag != "xmeml":
        errors.append("root is not xmeml")
    clips = root.findall("./sequence/media/video/track/clipitem")
    if not clips:
        errors.append("no video clipitem")
    transitions = root.findall("./sequence/media/video/track/transitionitem")
    keyframes = root.findall(".//filter/effect/name")
    if not transitions:
        warnings.append("no video transitionitem")
    if not root.findall("./sequence/media/audio/track/clipitem"):
        errors.append("no audio clipitem")
    if len(clips) > 1 and len(transitions) < len(clips) - 1:
        warnings.append("some joins have no transition")
    titles = root.findall("./sequence/media/video/track/generatoritem")
    markers = root.findall("./sequence/marker")
    color = root.findall("./sequence/media/video/track/clipitem/filter")
    tracks = root.findall("./sequence/media/video/track")
    return _result(
        path,
        errors,
        warnings=warnings,
        clips=len(clips),
        transitions=len(transitions),
        effects=len(keyframes),
        titles=len(titles),
        markers=len(markers),
        color_filters=len(color),
        video_tracks=len(tracks),
    )


def _validate_kdenlive(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return _result(path, ["missing file"])
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return _result(path, [f"parse error: {exc}"])
    if root.tag != "mlt":
        errors.append("root is not mlt")
    if root.find("profile") is None:
        errors.append("missing profile")
    playlists = [
        root.find("./playlist[@id='playlist_v1']"),
        root.find("./playlist[@id='playlist_v2']"),
    ]
    video_entries = [
        entry
        for playlist in playlists
        if playlist is not None
        for entry in playlist.findall("entry")
    ]
    if not video_entries:
        errors.append("no video playlist entries")
    if not root.findall("./chain"):
        errors.append("no media chain")
    affine = root.findall(".//property[@name='mlt_service'][.='affine']")
    if not affine:
        warnings.append("no affine transform filters")
    clips = len(video_entries)
    transitions = root.findall(".//transition")
    if clips > 1 and not any(
        item.findtext("property[@name='mlt_service']") in {"qtblend", "mix"} for item in transitions
    ):
        warnings.append("some joins have no transition")
    titles = root.findall("./producer/property[.='kdenlivetitle']")
    guides = root.findall(
        "./playlist[@id='main_bin']/property[@name='kdenlive:docproperties.guides']"
    )
    overlay = root.findall("./playlist[@id='playlist4']")
    stem = root.findall("./playlist[@id='playlist5']")
    color = root.findall(
        ".//playlist/entry/filter/property[@name='mlt_service'][.='lift_gamma_gain']"
    )
    return _result(
        path,
        errors,
        warnings=warnings,
        clips=clips,
        affine_filters=len(affine),
        tractors=len(root.findall("tractor")),
        titles=len(titles),
        guides=len(guides),
        overlay_track=len(overlay),
        audio_stem=len(stem),
        color_filters=len(color),
    )


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python scripts/validate_nle.py <exports-dir>", file=sys.stderr)
        return 2
    report = validate_nle_exports(Path(args[0]))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1
