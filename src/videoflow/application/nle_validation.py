"""Structural validation for the XML NLE exports."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def validate_nle_exports(directory: Path) -> dict[str, Any]:
    directory = Path(directory).expanduser()
    checks: dict[str, dict[str, Any]] = {}
    for name, validator in (
        ("fcpxml", _validate_fcpxml),
        ("xmeml", _validate_xmeml),
        ("kdenlive", _validate_kdenlive),
    ):
        filename = "timeline.xml" if name == "xmeml" else f"timeline.{name}"
        path = directory / filename
        checks[name] = validator(path)
    ok = all(item["ok"] for item in checks.values())
    return {"ok": ok, "directory": str(directory), "exports": checks}


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
    return _result(
        path,
        errors,
        warnings=warnings,
        clips=len(clips),
        transitions=len(transitions),
        keyframes=len(keyframes),
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
    return _result(
        path,
        errors,
        warnings=warnings,
        clips=len(clips),
        transitions=len(transitions),
        effects=len(keyframes),
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
    playlist = root.find("./playlist[@id='playlist0']")
    if playlist is None or not playlist.findall("entry"):
        errors.append("no video playlist entries")
    if not root.findall("./chain"):
        errors.append("no media chain")
    affine = root.findall(".//property[@name='mlt_service'][.='affine']")
    if not affine:
        warnings.append("no affine transform filters")
    return _result(
        path,
        errors,
        warnings=warnings,
        clips=len(playlist.findall("entry")) if playlist is not None else 0,
        affine_filters=len(affine),
        tractors=len(root.findall("tractor")),
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
