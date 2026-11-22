"""Decoupage calibration step for a human-edited reference timeline."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.decoupage_calibration import calibrate, write_report
from videoflow.core.context import PipelineContext
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


class DecoupageCalibrateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_path: str = Field(default="", max_length=4000)
    use_current_timeline: bool = True


@register_step
class DecoupageCalibrateStep(BaseStep):
    type = "decoupage.calibrate"
    title = "Calibrate decoupage"
    description = (
        "Read a Premiere XMEML/FCPXML reference edit, compare its source ranges "
        "with the current timeline, and write a calibration profile for retakes."
    )
    status = "available"
    icon = "⇄"
    color = "#f59e0b"
    requires = ("ingest",)
    produces = ("decoupage_profile",)
    params_model = DecoupageCalibrateParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = DecoupageCalibrateParams.model_validate(params)
        raw = options.baseline_path.strip()
        media = require_media(context)
        if not raw:
            payload = {
                "available": False,
                "reason": "No reference XML configured; retakes use the recipe defaults.",
            }
            target = context.output / "decoupage" / "profile.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            context.metadata["decoupage_profile"] = payload
            context.artifacts["decoupage_profile"] = str(target)
            context.warnings.append(
                "Decoupage calibration skipped: no reference XML configured."
            )
            io.report(100, "No reference XML; calibration skipped")
            return
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = context.output / candidate
        path = resolve_allowed(candidate, allowed_roots())
        if not path.is_file():
            payload = {
                "available": False,
                "reason": f"Reference XML is missing: {path}",
            }
            target = context.output / "decoupage" / "profile.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            context.metadata["decoupage_profile"] = payload
            context.artifacts["decoupage_profile"] = str(target)
            context.warnings.append(
                f"Decoupage calibration skipped: missing {path.name}."
            )
            io.report(100, "Reference XML missing; calibration skipped")
            return
        current: list[tuple[int, int]] = []
        if options.use_current_timeline and context.state is not None:
            current = [
                (segment.source_in_frame, segment.source_out_frame)
                for segment in context.state.video_segments
            ]
        report = calibrate(
            path,
            source_duration_frames=media.duration_frames,
            current_ranges=current,
        )
        json_path, markdown_path = write_report(context.output / "decoupage", report)
        payload = report.to_dict()
        payload["available"] = True
        payload["markdown"] = str(markdown_path)
        context.metadata["decoupage_profile"] = payload
        context.artifacts["decoupage_profile"] = str(json_path)
        context.artifacts["decoupage_profile_md"] = str(markdown_path)
        context.hashes["decoupage.calibrate"] = digest_payload(payload)
        io.report(
            100,
            f"{report.baseline_cut_count} reference cut(s); "
            f"{report.recommended_strictness} retake profile",
        )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("decoupage_profile", "decoupage_profile_md")
            if context.artifacts.get(key)
        )
