"""Deterministic ASS caption effect and layout QA."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.qa_caption import audit_ass
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import RecipeError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class CaptionEffectParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = ""
    effect: str = ""
    max_chars: int = Field(default=0, ge=0, le=400)
    strict: bool = False


@register_step
class CaptionEffectStep(BaseStep):
    type = "qa.caption_effect"
    title = "Caption effect QA"
    description = "Validate karaoke tags, durations, escapes, and line width in the ASS sidecar."
    produces = ("caption_effect_report",)
    params_model = CaptionEffectParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CaptionEffectParams.model_validate(params)
        style = context.state.modules_config.shorts.caption_style if context.state else None
        effect = options.effect or (style.effect if style is not None else "static")
        candidate = Path(options.path).expanduser() if options.path else None
        if candidate is None or not candidate.is_file():
            for key in ("captions_ass", "subtitles_ass"):
                value = context.artifacts.get(key)
                if value and Path(value).is_file():
                    candidate = Path(value)
                    break
        if candidate is None:
            for relative in ("captions/captions.ass", "subtitles.ass"):
                path = context.output / relative
                if path.is_file():
                    candidate = path
                    break
        if candidate is None:
            report = {"ok": True, "skipped": True, "issues": []}
        else:
            max_chars = options.max_chars
            if not max_chars and style is not None and context.media is not None:
                max_chars = round(
                    style.max_width
                    * context.media.width
                    / max(1.0, style.font_size * 0.55)
                )
            report = audit_ass(candidate, effect=effect, max_chars=max_chars)
            report["effect"] = effect
        path = context.work / "qa" / "caption_effect.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.metadata["caption_effect"] = report
        context.artifacts["caption_effect"] = str(path)
        if options.strict and not report.get("ok"):
            raise RecipeError(
                f"Caption effect QA found {len(report.get('issues', []))} issue(s); see {path}"
            )
        io.report(100, f"Caption effect QA: {len(report.get('issues', []))} issue(s)")


__all__ = ["CaptionEffectStep"]
