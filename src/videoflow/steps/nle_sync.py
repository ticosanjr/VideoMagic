"""Read an external NLE timeline and report/apply sync changes."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import NleSyncReport
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.timebase import Rounding
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class NleSyncParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = Field(default="fcpxml", pattern="^(fcpxml|mlt|resolve)$")
    path: str = ""
    apply: bool = False
    conflict_policy: str = Field(
        default="report", pattern="^(report|prefer_external|prefer_internal)$"
    )


def _seconds(raw: str) -> float:
    value = raw.strip()
    if value.endswith("s"):
        value = value[:-1]
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            return float(numerator) / max(1e-9, float(denominator))
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _clip_count(path: Path, fmt: str) -> int:
    return len(_clip_ranges(path, fmt, 30.0))


def _clip_ranges(path: Path, fmt: str, fps: float) -> list[tuple[float, float]]:
    """Return external clip start/duration pairs in seconds."""

    root = ET.parse(path).getroot()
    ranges: list[tuple[float, float]] = []
    if fmt == "fcpxml":
        names = {"clip", "asset-clip"}
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] not in names:
                continue
            duration = _seconds(node.get("duration", ""))
            if duration <= 0:
                continue
            offset = _seconds(node.get("offset", "0s"))
            ranges.append((max(0.0, offset), duration))
        return ranges
    cursor = 0.0
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "entry":
            continue
        start = _seconds(node.get("in", "0"))
        end = _seconds(node.get("out", "0"))
        duration = max(0.0, (end - start + 1) / max(1.0, fps))
        if duration <= 0:
            continue
        ranges.append((cursor, duration))
        cursor += duration
    return ranges


@register_step
class NleSyncStep(BaseStep):
    type = "nle.sync_back"
    status = "partial"
    icon = "⇄"
    color = "#3b82f6"
    title = "NLE sync back"
    description = "Read FCPXML/MLT cuts and report/apply transcript, B-roll, and ducking sync."
    requires = ()
    produces = ("sync_back_report",)
    params_model = NleSyncParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = NleSyncParams.model_validate(params)
        warnings: list[str] = []
        conflicts: list[str] = []
        changed = 0
        if not options.path.strip():
            warnings.append("No external NLE path supplied; report only")
        else:
            path = resolve_allowed(Path(options.path), allowed_roots())
            if not path.is_file():
                warnings.append(f"NLE file not found: {path}")
            elif options.format == "resolve":
                warnings.append("Resolve roundtrip requires the Resolve MCP adapter")
            else:
                try:
                    fps = (
                        context.media.fps_num / context.media.fps_den
                        if context.media is not None
                        else 30.0
                    )
                    ranges = _clip_ranges(path, options.format, fps)
                    external = len(ranges)
                except (OSError, ET.ParseError) as exc:
                    warnings.append(f"Could not parse {path.name}: {exc}")
                    external = 0
                    ranges = []
                internal = len(context.state.video_segments) if context.state else 0
                changed = abs(external - internal)
                if changed:
                    conflicts.append(f"external has {external} clip(s), internal has {internal}")
                if (
                    options.apply
                    and context.state is not None
                    and context.media is not None
                    and ranges
                    and not conflicts
                ):
                    timebase = context.media.timebase()
                    segments = []
                    for segment, (start, duration) in zip(
                        context.state.video_segments, ranges, strict=False
                    ):
                        in_frame = timebase.seconds_to_frames(
                            Fraction(str(start)), Rounding.NEAREST
                        )
                        out_frame = timebase.seconds_to_frames(
                            Fraction(str(start + duration)), Rounding.NEAREST
                        )
                        if out_frame <= in_frame:
                            conflicts.append(f"external clip {segment.clip_id} has no duration")
                            break
                        segments.append(
                            segment.model_copy(
                                update={
                                    "timeline_in_frame": in_frame,
                                    "timeline_out_frame": out_frame,
                                }
                            )
                        )
                    if segments and not conflicts:
                        context.state = context.state.model_copy(
                            update={
                                "video_segments": segments,
                                "revision": context.state.revision + 1,
                            }
                        )
                        changed = len(segments)
        applied = bool(options.apply and not conflicts and changed)
        report = NleSyncReport(
            format=options.format,
            applied=applied,
            changed_clips=changed if applied else 0,
            conflicts=conflicts,
            transcript_updates=0,
            broll_updates=0,
            warnings=warnings,
        )
        path = context.work / "nle_sync_report.json"
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.metadata["sync_back_report"] = report.model_dump(mode="json")
        context.artifacts["sync_back_report"] = str(path)
        if conflicts and options.apply and options.conflict_policy == "report":
            context.warnings.extend(conflicts)
        io.report(100, f"NLE sync: {changed} changed clip(s)")
