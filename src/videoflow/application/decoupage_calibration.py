"""Reference-edit calibration from Premiere XMEML or FCPXML timelines."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from videoflow.domain.errors import IngestError


@dataclass(frozen=True, slots=True)
class SourceRange:
    source_in_frame: int
    source_out_frame: int
    timeline_in_frame: int
    timeline_out_frame: int


@dataclass
class CalibrationReport:
    baseline_path: str
    format: str
    fps: float
    source_duration_frames: int
    baseline_cut_count: int
    baseline_duration_frames: int
    kept_ratio: float
    source_ranges: list[SourceRange] = field(default_factory=list)
    current_cut_count: int = 0
    overlap_ratio: float = 0.0
    recommended_strictness: str = "balanced"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_path": self.baseline_path,
            "format": self.format,
            "fps": round(self.fps, 6),
            "source_duration_frames": self.source_duration_frames,
            "baseline_cut_count": self.baseline_cut_count,
            "baseline_duration_frames": self.baseline_duration_frames,
            "kept_ratio": round(self.kept_ratio, 4),
            "current_cut_count": self.current_cut_count,
            "overlap_ratio": round(self.overlap_ratio, 4),
            "recommended_strictness": self.recommended_strictness,
            "warnings": list(self.warnings),
            "source_ranges": [
                {
                    "source_in_frame": item.source_in_frame,
                    "source_out_frame": item.source_out_frame,
                    "timeline_in_frame": item.timeline_in_frame,
                    "timeline_out_frame": item.timeline_out_frame,
                }
                for item in self.source_ranges
            ],
        }


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(round(float(str(value or default))))
    except (TypeError, ValueError):
        return default


def _time_frames(value: str | None, fps: float) -> int:
    """Parse an FCPXML time such as ``1001/24000s`` or ``12s`` into frames."""

    text = str(value or "").strip()
    if not text:
        return 0
    has_seconds = text.endswith("s")
    text = text.removesuffix("s")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            seconds = float(numerator) / float(denominator)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0
        return int(round(seconds * fps))
    try:
        number = float(text)
    except ValueError:
        return 0
    if has_seconds or "." in text:
        return int(round(number * fps))
    return int(round(number))


def _xmeml_fps(root: ElementTree.Element) -> float:
    rate = root.find(".//rate")
    if rate is None:
        return 24.0
    timebase = _int(rate.findtext("timebase"), 24)
    ntsc = str(rate.findtext("ntsc") or "").casefold() in {"true", "1"}
    return timebase * 1000 / 1001 if ntsc else float(timebase)


def _fcpxml_fps(root: ElementTree.Element) -> float:
    for element in root.iter():
        frame_duration = element.attrib.get("frameDuration")
        if not frame_duration:
            continue
        raw = frame_duration.removesuffix("s")
        if "/" in raw:
            numerator, denominator = raw.split("/", 1)
            try:
                seconds = float(numerator) / float(denominator)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if seconds > 0:
                return 1.0 / seconds
    return 24.0


def _xmeml_ranges(root: ElementTree.Element) -> list[SourceRange]:
    ranges = []
    for clip in root.iter("clipitem"):
        start = _int(clip.findtext("start"))
        end = _int(clip.findtext("end"))
        source_in = _int(clip.findtext("in"), start)
        source_out = _int(clip.findtext("out"), end)
        if source_out <= source_in:
            source_out = source_in + max(1, end - start)
        ranges.append(
            SourceRange(
                source_in_frame=source_in,
                source_out_frame=source_out,
                timeline_in_frame=start,
                timeline_out_frame=max(start, end),
            )
        )
    return ranges


def _fcpxml_ranges(root: ElementTree.Element, fps: float) -> list[SourceRange]:
    ranges = []
    for tag in ("asset-clip", "clip", "video"):
        for clip in root.iter(tag):
            duration = _time_frames(
                clip.attrib.get("duration") or clip.findtext("duration"), fps
            )
            if duration <= 0:
                continue
            offset = _time_frames(
                clip.attrib.get("offset") or clip.findtext("offset"), fps
            )
            start = _time_frames(
                clip.attrib.get("start") or clip.findtext("start"), fps
            )
            ranges.append(
                SourceRange(
                    source_in_frame=start,
                    source_out_frame=start + duration,
                    timeline_in_frame=offset,
                    timeline_out_frame=offset + duration,
                )
            )
    return ranges


def read_baseline(path: Path) -> tuple[str, float, list[SourceRange]]:
    target = Path(path).expanduser()
    if not target.is_file():
        raise IngestError(f"Reference timeline does not exist: {target}")
    try:
        root = ElementTree.fromstring(target.read_bytes())
    except (OSError, ElementTree.ParseError) as exc:
        raise IngestError(f"Cannot parse reference timeline: {exc}") from exc
    tag = root.tag.casefold()
    if "xmeml" in tag or root.find(".//clipitem") is not None:
        fps = _xmeml_fps(root)
        ranges = _xmeml_ranges(root)
        return "xmeml", fps, ranges
    if "fcpxml" in tag or root.find(".//asset-clip") is not None:
        fps = _fcpxml_fps(root)
        ranges = _fcpxml_ranges(root, fps)
        return "fcpxml", fps, ranges
    raise IngestError("Reference timeline is neither XMEML nor FCPXML.")


def _intersection(
    left: SourceRange, right: tuple[int, int]
) -> int:
    start = max(left.source_in_frame, right[0])
    end = min(left.source_out_frame, right[1])
    return max(0, end - start)


def calibrate(
    baseline_path: Path,
    *,
    source_duration_frames: int,
    current_ranges: list[tuple[int, int]] = (),
) -> CalibrationReport:
    fmt, fps, ranges = read_baseline(baseline_path)
    kept = sum(max(0, item.source_out_frame - item.source_in_frame) for item in ranges)
    duration = max(1, int(source_duration_frames))
    kept_ratio = min(1.0, kept / duration)
    if kept_ratio >= 0.85:
        strictness = "conservative"
    elif kept_ratio >= 0.60:
        strictness = "balanced"
    else:
        strictness = "aggressive"
    overlap = 0
    total = 0
    for item in ranges:
        length = max(0, item.source_out_frame - item.source_in_frame)
        total += length
        overlap += max(
            (_intersection(item, current) for current in current_ranges),
            default=0,
        )
    report = CalibrationReport(
        baseline_path=str(baseline_path),
        format=fmt,
        fps=fps,
        source_duration_frames=duration,
        baseline_cut_count=len(ranges),
        baseline_duration_frames=kept,
        kept_ratio=kept_ratio,
        source_ranges=ranges,
        current_cut_count=len(current_ranges),
        overlap_ratio=(overlap / total) if total else 0.0,
        recommended_strictness=strictness,
    )
    return report


def write_report(directory: Path, report: CalibrationReport) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "profile.json"
    markdown_path = directory / "profile.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Decoupage calibration",
        "",
        f"- Reference: `{report.baseline_path}`",
        f"- Format: {report.format} at {report.fps:.3f} fps",
        f"- Reference cuts: {report.baseline_cut_count}",
        f"- Kept ratio: {report.kept_ratio:.1%}",
        f"- Recommended retake strictness: **{report.recommended_strictness}**",
        f"- Current cuts: {report.current_cut_count}",
        f"- Source overlap with the reference: {report.overlap_ratio:.1%}",
    ]
    if report.warnings:
        lines.extend(["", "## Warnings", *[f"- {item}" for item in report.warnings]])
    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, markdown_path
