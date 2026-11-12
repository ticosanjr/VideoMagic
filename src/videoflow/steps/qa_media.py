"""Frame, transcript, and repair QA for both delivery flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.qa_media import compare_text, detect_black, detect_freeze
from videoflow.application.vision_analysis import extract_frames
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _video(context: PipelineContext) -> Path | None:
    for key in ("video", "video_master", "video_draft"):
        value = context.artifacts.get(key)
        if value and Path(value).is_file():
            return Path(value)
    return Path(context.source) if Path(context.source).is_file() else None


class QaFramesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    black_min_seconds: float = Field(default=0.15, ge=0.01, le=5.0)
    freeze_min_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    sample_fps: float = Field(default=1.0, gt=0.0, le=10.0)
    max_frames: int = Field(default=60, ge=1, le=600)


@register_step
class QaFramesStep(BaseStep):
    type = "qa.frames"
    title = "Frame QA"
    description = (
        "Detect black spans and static screens in the rendered master, and sample "
        "frames for the visual review gate."
    )
    status = "available"
    icon = "◉"
    color = "#22c55e"
    params_model = QaFramesParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = QaFramesParams.model_validate(params)
        video = _video(context)
        if video is None:
            raise ExportError("Frame QA requires a rendered video.")
        io.report(15, "Scanning black frames")
        issues = detect_black(video, min_duration=options.black_min_seconds)
        io.report(45, "Scanning static screens")
        issues.extend(detect_freeze(video, min_duration=options.freeze_min_seconds))
        frames: list[str] = []
        try:
            frames = [
                str(path)
                for path in extract_frames(
                    video,
                    context.output / "qa" / "frames",
                    fps=options.sample_fps,
                    max_frames=options.max_frames,
                    width=960,
                )
            ]
        except Exception as exc:  # noqa: BLE001 - frame sampling is best effort
            context.warnings.append(f"QA frame sampling skipped: {exc}")
        issues.extend(_empty_frame_issues(frames, options.sample_fps))
        issues.extend(_clipping_issues(context))
        critical = [item for item in issues if item.get("severity") == "critical"]
        payload = {
            "ok": True,
            "video": str(video),
            "issues": issues,
            "critical_count": len(critical),
            "warning_count": len(issues) - len(critical),
            "passed": not critical,
            "frames": frames,
        }
        target = context.output / "qa" / "frames.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["qa_frames"] = str(target)
        context.metadata["qa_frames"] = payload
        context.hashes["qa.frames"] = digest_payload(
            {"issues": len(issues), "frames": len(frames)}
        )
        if critical:
            context.warnings.append(
                f"Frame QA found {len(critical)} critical issue(s)."
            )
        io.report(
            100,
            f"{len(issues)} issue(s); {len(frames)} frame(s) sampled",
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("qa_frames")
        return (Path(path),) if path else ()


def _clipping_issues(context: PipelineContext) -> list[dict[str, Any]]:
    """Flag OCR boxes that touch a frame border, a common render clipping bug."""

    payload = _load(context.output / "vision" / "ocr.json", {})
    issues: list[dict[str, Any]] = []
    for frame in payload.get("frames", []) if isinstance(payload, dict) else []:
        if not isinstance(frame, dict):
            continue
        width = int(frame.get("width") or 0)
        height = int(frame.get("height") or 0)
        if width <= 0 or height <= 0:
            continue
        for box in frame.get("boxes", []):
            if not isinstance(box, dict):
                continue
            x = int(box.get("x") or 0)
            y = int(box.get("y") or 0)
            box_width = int(box.get("width") or 0)
            box_height = int(box.get("height") or 0)
            if x <= 1 or y <= 1 or x + box_width >= width - 1 or y + box_height >= height - 1:
                issues.append(
                    {
                        "kind": "text_clipped",
                        "severity": "warning",
                        "start_sec": float(frame.get("time_sec") or 0.0),
                        "end_sec": float(frame.get("time_sec") or 0.0),
                        "message": (
                            "OCR text box touches the frame border: "
                            f"{str(box.get('text') or '')[:60]}"
                        ),
                    }
                )
    return issues


def _empty_frame_issues(
    frames: list[str], sample_fps: float
) -> list[dict[str, Any]]:
    """Catch near-uniform frames that blackdetect does not report as black."""

    try:
        from PIL import Image, ImageStat
    except Exception:
        return []
    issues: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        try:
            with Image.open(frame) as image:
                stat = ImageStat.Stat(image.convert("L"))
        except Exception:
            continue
        mean = float(stat.mean[0]) if stat.mean else 0.0
        stddev = float(stat.stddev[0]) if stat.stddev else 0.0
        if stddev < 2.0 and mean < 12.0:
            issues.append(
                {
                    "kind": "empty_frame",
                    "severity": "critical",
                    "start_sec": round(index / max(0.01, sample_fps), 3),
                    "end_sec": round((index + 1) / max(0.01, sample_fps), 3),
                    "message": "Near-uniform dark frame; likely an empty scene.",
                }
            )
        elif stddev < 2.0 and mean > 245.0:
            issues.append(
                {
                    "kind": "empty_frame",
                    "severity": "warning",
                    "start_sec": round(index / max(0.01, sample_fps), 3),
                    "end_sec": round((index + 1) / max(0.01, sample_fps), 3),
                    "message": "Near-uniform light frame; check the layout.",
                }
            )
    return issues


class QaTranscriptParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_path: str = Field(default="script/narration.txt", max_length=2000)
    transcript_path: str = Field(
        default="narration/transcript.json", max_length=2000
    )
    min_similarity: float = Field(default=0.90, ge=0.0, le=1.0)


def _reference_text(context: PipelineContext, path: str) -> str:
    candidate = context.output / path
    try:
        text = candidate.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        return text
    payload = _load(context.output / "script" / "script.json", {})
    sections = payload.get("sections", []) if isinstance(payload, dict) else []
    return "\n".join(
        str(item.get("narration") or "")
        for item in sections
        if isinstance(item, dict)
    )


def _hypothesis_text(context: PipelineContext, path: str) -> tuple[str, bool]:
    payload = _load(context.output / path, {})
    sentences = payload.get("sentences", []) if isinstance(payload, dict) else []
    text = "\n".join(
        str(item.get("text") or "")
        for item in sentences
        if isinstance(item, dict)
    )
    if text.strip():
        return text, True
    return "\n".join(sentence.text for sentence in context.transcript), False


@register_step
class QaTranscriptStep(BaseStep):
    type = "qa.transcript"
    title = "Transcript audit"
    description = (
        "Compare the spoken transcript against the approved script and report "
        "missing or extra words before delivery."
    )
    status = "available"
    icon = "≟"
    color = "#22c55e"
    params_model = QaTranscriptParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = QaTranscriptParams.model_validate(params)
        reference = _reference_text(context, options.reference_path)
        hypothesis, independent = _hypothesis_text(context, options.transcript_path)
        if not reference.strip():
            context.warnings.append("Transcript audit skipped: no script reference.")
            io.report(100, "No script reference; audit skipped")
            return
        if not hypothesis.strip():
            context.warnings.append("Transcript audit skipped: no spoken transcript.")
            io.report(100, "No spoken transcript; audit skipped")
            return
        result = compare_text(reference, hypothesis)
        result["independent_transcript"] = independent
        result["passed"] = (
            float(result["similarity"]) >= options.min_similarity
        )
        target = context.output / "qa" / "transcript.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        context.artifacts["qa_transcript"] = str(target)
        context.metadata["qa_transcript"] = result
        context.hashes["qa.transcript"] = digest_payload(result)
        if not result["passed"]:
            context.warnings.append(
                "Transcript audit below threshold: "
                f"{float(result['similarity']):.1%}."
            )
        io.report(100, f"Transcript similarity {float(result['similarity']):.1%}")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("qa_transcript")
        return (Path(path),) if path else ()


class QaRepairParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_items: int = Field(default=100, ge=1, le=500)


@register_step
class QaRepairStep(BaseStep):
    type = "qa.repair"
    title = "QA repair plan"
    description = (
        "Map QA issues back to units and scenes, then write the approved repair "
        "plan without re-rendering automatically."
    )
    status = "available"
    icon = "⟲"
    color = "#f59e0b"
    params_model = QaRepairParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = QaRepairParams.model_validate(params)
        frames = _load(context.output / "qa" / "frames.json", {})
        transcript = _load(context.output / "qa" / "transcript.json", {})
        vision = _load(context.output / "qa" / "vision-report.json", {})
        units_payload = _load(context.output / "storyboard" / "units.json", {})
        units = (
            units_payload.get("units", [])
            if isinstance(units_payload, dict)
            else units_payload
        )
        issues: list[dict[str, Any]] = []
        for source_name, payload in (
            ("frames", frames),
            ("vision", vision),
        ):
            for item in payload.get("issues", []) if isinstance(payload, dict) else []:
                if isinstance(item, dict):
                    issues.append({**item, "source": source_name})
        if isinstance(transcript, dict) and not transcript.get("passed", True):
            issues.append(
                {
                    "kind": "transcript_mismatch",
                    "severity": "warning",
                    "message": "Spoken transcript differs from the script.",
                    "similarity": transcript.get("similarity"),
                    "source": "transcript",
                }
            )
        items: list[dict[str, Any]] = []
        for issue in issues[: options.max_items]:
            start = float(issue.get("start_sec") or 0.0)
            unit = next(
                (
                    item
                    for item in units
                    if isinstance(item, dict)
                    and float(item.get("start_sec") or 0.0)
                    <= start
                    <= float(item.get("end_sec") or 0.0)
                ),
                None,
            )
            items.append(
                {
                    **issue,
                    "unit_id": (unit or {}).get("unit_id", ""),
                    "action": (
                        "Re-render the unit with the corrected scene code."
                        if unit
                        else "Review the timeline span and re-run QA."
                    ),
                }
            )
        payload = {
            "ok": True,
            "issues": items,
            "count": len(items),
            "needs_review": bool(items),
            "note": "Repairs are manual by design; no scene is re-rendered here.",
        }
        target = context.output / "qa" / "repair-plan.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        markdown = context.output / "qa" / "repair-plan.md"
        lines = ["# QA repair plan", ""]
        for item in items:
            lines.append(
                f"- **{item.get('severity', 'warning')}** "
                f"{item.get('kind', 'issue')} "
                f"({item.get('unit_id') or 'timeline'}): {item.get('message', '')}"
            )
        markdown.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.artifacts["qa_repair"] = str(target)
        context.artifacts["qa_repair_md"] = str(markdown)
        context.metadata["qa_repair"] = payload
        context.hashes["qa.repair"] = digest_payload(payload)
        io.report(100, f"{len(items)} repair item(s) prepared")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("qa_repair", "qa_repair_md")
            if context.artifacts.get(key)
        )


__all__ = [
    "QaFramesParams",
    "QaFramesStep",
    "QaRepairParams",
    "QaRepairStep",
    "QaTranscriptParams",
    "QaTranscriptStep",
]
