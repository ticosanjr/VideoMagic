"""Read an external NLE timeline and report/apply sync changes."""

from __future__ import annotations

import json
import re
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

    format: str = Field(default="fcpxml", pattern="^(fcpxml|mlt|xmeml|resolve)$")
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


_MARKER_KEY = re.compile(r"^vf[\s:]+", re.IGNORECASE)


def _timecode_seconds(raw: str) -> float:
    """Parse ``HH:MM:SS.mmm`` or a plain second count."""

    value = raw.strip()
    if not value:
        return 0.0
    if ":" in value:
        parts = value.split(":")
        try:
            numbers = [float(part.replace(",", ".")) for part in parts]
        except ValueError:
            return 0.0
        total = 0.0
        for number in numbers:
            total = total * 60 + number
        return total
    return _seconds(value)


def _marker_value(node: ET.Element) -> str:
    for key in ("value", "text", "name", "note"):
        raw = node.get(key)
        if raw:
            return raw
    return ""


def _marker_params(kind: str, raw: str) -> tuple[str, dict[str, str]] | None:
    text = _MARKER_KEY.sub("", raw.strip())
    if not text:
        return None
    parts = re.split(r"[:\s]+", text, maxsplit=1)
    name = parts[0].strip().lower()
    if name not in {"transcript", "broll", "b-roll", "ducking", "duck"}:
        return None
    params: dict[str, str] = {}
    for chunk in re.split(r"[;,\s]+", parts[1] if len(parts) > 1 else ""):
        if not chunk:
            continue
        key, separator, value = chunk.partition("=")
        if separator:
            params[key.strip().lower()] = value.strip()
    if name == "b-roll":
        name = "broll"
    if name == "duck":
        name = "ducking"
    return name, params


def _markers(
    path: Path, fmt: str, fps: float = 30.0
) -> list[tuple[str, float, float, dict[str, str]]]:
    """Read ``vf transcript/broll/ducking`` markers from an NLE timeline.

    FCPXML uses ``<marker start="12s" duration="2s" value="vf:..."/>``.
    Kdenlive/MLT uses ``<marker in="00:00:12.000" out="00:00:14.000"
    text="vf:..."/>``.
    """

    root = ET.parse(path).getroot()
    markers: list[tuple[str, float, float, dict[str, str]]] = []
    if fmt == "xmeml":
        for node in root.findall("./sequence/marker"):
            parsed = _marker_params("", node.findtext("name") or node.findtext("comment") or "")
            if parsed is None:
                continue
            kind, params = parsed
            try:
                start_frame = float(node.findtext("in") or 0)
                out_frame = float(node.findtext("out") or start_frame)
            except ValueError:
                start_frame, out_frame = 0.0, 0.0
            start = start_frame / max(1.0, fps)
            duration = max(0.0, (out_frame - start_frame) / max(1.0, fps))
            markers.append((kind, start, duration, params))
        return markers
    names = {"marker", "chapter-marker"}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in names:
            continue
        parsed = _marker_params("", _marker_value(node))
        if parsed is None:
            continue
        kind, params = parsed
        if node.get("start") is not None:
            start = _seconds(node.get("start", "0s"))
            duration = _seconds(node.get("duration", "0s"))
        else:
            start = _timecode_seconds(node.get("in", "0"))
            out = _timecode_seconds(node.get("out", "0"))
            duration = max(0.0, out - start)
        markers.append((kind, start, duration, params))
    return markers


def _float_param(params: dict[str, str], key: str, default: float) -> float:
    try:
        return float(params[key])
    except (KeyError, TypeError, ValueError):
        return default


def _apply_markers(
    context: PipelineContext,
    markers: list[tuple[str, float, float, dict[str, str]]],
) -> tuple[int, int, int, list[str]]:
    """Apply transcript shifts, B-roll cues, and ducking levels."""

    transcript_updates = 0
    broll_updates = 0
    ducking_updates = 0
    warnings: list[str] = []
    rate = context.media.audio_sample_rate if context.media is not None else 48000
    broll_plan = context.metadata.get("broll_plan")
    if not isinstance(broll_plan, dict):
        broll_plan = {}
    ducking = context.metadata.get("nle_ducking")
    if not isinstance(ducking, list):
        ducking = []
    for kind, start, duration, params in markers:
        if kind == "transcript":
            try:
                shift = float(params.get("shift", params.get("offset", "0")))
            except (TypeError, ValueError):
                warnings.append(f"Invalid transcript shift marker at {start:.3f}s")
                continue
            if shift == 0:
                continue
            shift_samples = int(round(shift * rate))
            changed = 0
            for index, sentence in enumerate(context.transcript):
                if start > 0 and sentence.start_sample / rate < start:
                    continue
                words = [
                    word.model_copy(
                        update={
                            "start_sample": max(0, word.start_sample + shift_samples),
                            "end_sample": max(0, word.end_sample + shift_samples),
                        }
                    )
                    for word in sentence.words
                ]
                context.transcript[index] = sentence.model_copy(
                    update={
                        "start_sample": max(0, sentence.start_sample + shift_samples),
                        "end_sample": max(0, sentence.end_sample + shift_samples),
                        "words": words,
                    }
                )
                changed += 1
            transcript_updates += changed
        elif kind == "broll":
            path = params.get("path", "")
            if not path:
                warnings.append(f"B-roll marker at {start:.3f}s has no path")
                continue
            title = params.get("title", "")
            if not title:
                if context.selected_shorts:
                    title = str(getattr(context.selected_shorts[0], "title", ""))
                elif context.shorts:
                    title = str(context.shorts[0].get("title") or "")
            entry = {
                "path": str(Path(path).expanduser()),
                "start_sec": max(0.0, _float_param(params, "start", start)),
                "duration_sec": max(0.1, _float_param(params, "duration", duration or 2.0)),
                "provider": "nle",
                "source": "nle_marker",
            }
            broll_plan.setdefault(title, []).append(entry)
            broll_updates += 1
        else:
            try:
                level = float(params.get("level", params.get("db", "-12")))
            except (TypeError, ValueError):
                warnings.append(f"Invalid ducking level marker at {start:.3f}s")
                continue
            end = _float_param(params, "end", start + duration)
            ducking.append(
                {
                    "start_sec": max(0.0, start),
                    "end_sec": max(start, end),
                    "level_db": max(-60.0, min(0.0, level)),
                }
            )
            ducking_updates += 1
    if transcript_updates and context.state is not None:
        context.state = context.state.model_copy(
            update={
                "transcript": context.transcript,
                "revision": context.state.revision + 1,
            }
        )
    if broll_updates:
        context.metadata["broll_plan"] = broll_plan
    if ducking_updates:
        context.metadata["nle_ducking"] = ducking
        target = context.output / "audio" / "ducking.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"ducking": ducking}, indent=2) + "\n", encoding="utf-8")
        context.artifacts["nle_ducking"] = str(target)
    return transcript_updates, broll_updates, ducking_updates, warnings


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
    if fmt == "xmeml":
        for node in root.findall("./sequence/media/video/track/clipitem"):
            try:
                start = float(node.findtext("start") or 0)
                end = float(node.findtext("end") or 0)
            except ValueError:
                continue
            duration = (end - start) / max(1.0, fps)
            if duration > 0:
                ranges.append((max(0.0, start / max(1.0, fps)), duration))
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
    description = "Read FCPXML/MLT cuts and apply transcript, B-roll, and ducking markers."
    requires = ()
    produces = ("sync_back_report",)
    params_model = NleSyncParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = NleSyncParams.model_validate(params)
        warnings: list[str] = []
        conflicts: list[str] = []
        changed = 0
        transcript_updates = 0
        broll_updates = 0
        ducking_updates = 0
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
                    markers = _markers(path, options.format, fps)
                    external = len(ranges)
                except (OSError, ET.ParseError) as exc:
                    warnings.append(f"Could not parse {path.name}: {exc}")
                    external = 0
                    ranges = []
                    markers = []
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
                if options.apply and markers:
                    marker_counts = _apply_markers(context, markers)
                    transcript_updates += marker_counts[0]
                    broll_updates += marker_counts[1]
                    ducking_updates += marker_counts[2]
                    warnings.extend(marker_counts[3])
        applied = bool(
            options.apply
            and not conflicts
            and (changed or transcript_updates or broll_updates or ducking_updates)
        )
        report = NleSyncReport(
            format=options.format,
            applied=applied,
            changed_clips=changed if applied and not conflicts else 0,
            conflicts=conflicts,
            transcript_updates=transcript_updates,
            broll_updates=broll_updates,
            ducking_updates=ducking_updates,
            warnings=warnings,
        )
        context.work.mkdir(parents=True, exist_ok=True)
        path = context.work / "nle_sync_report.json"
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        context.metadata["sync_back_report"] = report.model_dump(mode="json")
        context.artifacts["sync_back_report"] = str(path)
        if conflicts and options.apply and options.conflict_policy == "report":
            context.warnings.extend(conflicts)
        io.report(100, f"NLE sync: {changed} changed clip(s)")
